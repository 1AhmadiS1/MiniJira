from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Workspace, WorkspaceMember

User = get_user_model()

WORKSPACES_URL = "/api/workspaces/"
MEMBERS_URL = "/api/members/"


def make_user(email):
    return User.objects.create_user(
        email=email, password="supersecret123", first_name="T", last_name="U"
    )


class WorkspaceEndpointTests(APITestCase):
    def setUp(self):
        self.owner = make_user("owner@example.com")
        self.other = make_user("other@example.com")

    # --- workspace create / list ---

    def test_create_requires_auth(self):
        resp = self.client.post(WORKSPACES_URL, {"name": "WS"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_workspace_makes_creator_owner_member(self):
        """Point 1 & 5: creator is auto-added as an OWNER member, once."""
        self.client.force_authenticate(self.owner)
        resp = self.client.post(
            WORKSPACES_URL, {"name": "Team A"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        ws = Workspace.objects.get(id=resp.data["id"])
        self.assertEqual(ws.created_by, self.owner)
        member = WorkspaceMember.objects.get(workspace=ws, user=self.owner)
        self.assertEqual(member.role, WorkspaceMember.Role.OWNER)
        self.assertEqual(ws.memberships.count(), 1)

    def test_list_only_shows_workspaces_i_belong_to(self):
        self.client.force_authenticate(self.owner)
        self.client.post(WORKSPACES_URL, {"name": "Mine"}, format="json")

        # a workspace the owner is NOT part of
        foreign = Workspace.objects.create(name="Foreign", created_by=self.other)
        WorkspaceMember.objects.create(
            user=self.other, workspace=foreign, role=WorkspaceMember.Role.OWNER
        )

        resp = self.client.get(WORKSPACES_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        names = [w["name"] for w in resp.data]
        self.assertIn("Mine", names)
        self.assertNotIn("Foreign", names)

    # --- member add (point 6) ---

    def _create_workspace(self, user):
        self.client.force_authenticate(user)
        resp = self.client.post(WORKSPACES_URL, {"name": "WS"}, format="json")
        return resp.data["id"]

    def test_owner_can_add_member(self):
        ws_id = self._create_workspace(self.owner)
        self.client.force_authenticate(self.owner)
        resp = self.client.post(
            MEMBERS_URL,
            {"user": self.other.id, "workspace": ws_id, "role": "member"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            WorkspaceMember.objects.filter(
                user=self.other, workspace_id=ws_id
            ).exists()
        )

    def test_non_owner_cannot_add_member(self):
        """Point 6: a plain member cannot add members -> 403."""
        ws_id = self._create_workspace(self.owner)
        # owner adds `other` as a plain member
        self.client.force_authenticate(self.owner)
        self.client.post(
            MEMBERS_URL,
            {"user": self.other.id, "workspace": ws_id, "role": "member"},
            format="json",
        )
        # now `other` (member) tries to add a third user
        third = make_user("third@example.com")
        self.client.force_authenticate(self.other)
        resp = self.client.post(
            MEMBERS_URL,
            {"user": third.id, "workspace": ws_id, "role": "member"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_outsider_cannot_add_member(self):
        ws_id = self._create_workspace(self.owner)
        outsider = make_user("outsider@example.com")
        self.client.force_authenticate(outsider)
        resp = self.client.post(
            MEMBERS_URL,
            {"user": outsider.id, "workspace": ws_id, "role": "member"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # --- member delete (point 7) ---

    def test_member_can_leave_own_membership(self):
        """Point 7: a user may DELETE their own membership (leave)."""
        ws_id = self._create_workspace(self.owner)
        self.client.force_authenticate(self.owner)
        self.client.post(
            MEMBERS_URL,
            {"user": self.other.id, "workspace": ws_id, "role": "member"},
            format="json",
        )
        row = WorkspaceMember.objects.get(user=self.other, workspace_id=ws_id)

        self.client.force_authenticate(self.other)
        resp = self.client.delete(f"{MEMBERS_URL}{row.id}/")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            WorkspaceMember.objects.filter(id=row.id).exists()
        )

    def test_member_cannot_delete_someone_elses_membership(self):
        ws_id = self._create_workspace(self.owner)
        self.client.force_authenticate(self.owner)
        self.client.post(
            MEMBERS_URL,
            {"user": self.other.id, "workspace": ws_id, "role": "member"},
            format="json",
        )
        owner_row = WorkspaceMember.objects.get(user=self.owner, workspace_id=ws_id)

        # `other` (plain member) tries to delete the OWNER's membership
        self.client.force_authenticate(self.other)
        resp = self.client.delete(f"{MEMBERS_URL}{owner_row.id}/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(WorkspaceMember.objects.filter(id=owner_row.id).exists())

    def test_owner_can_remove_member(self):
        ws_id = self._create_workspace(self.owner)
        self.client.force_authenticate(self.owner)
        self.client.post(
            MEMBERS_URL,
            {"user": self.other.id, "workspace": ws_id, "role": "member"},
            format="json",
        )
        row = WorkspaceMember.objects.get(user=self.other, workspace_id=ws_id)
        resp = self.client.delete(f"{MEMBERS_URL}{row.id}/")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    # --- member update / role change (point 7, PATCH) ---

    def test_non_owner_cannot_change_role(self):
        """A plain member cannot PATCH another member's role -> 403."""
        ws_id = self._create_workspace(self.owner)
        self.client.force_authenticate(self.owner)
        self.client.post(
            MEMBERS_URL,
            {"user": self.other.id, "workspace": ws_id, "role": "member"},
            format="json",
        )
        owner_row = WorkspaceMember.objects.get(user=self.owner, workspace_id=ws_id)
        self.client.force_authenticate(self.other)
        resp = self.client.patch(
            f"{MEMBERS_URL}{owner_row.id}/", {"role": "member"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_change_role(self):
        ws_id = self._create_workspace(self.owner)
        self.client.force_authenticate(self.owner)
        self.client.post(
            MEMBERS_URL,
            {"user": self.other.id, "workspace": ws_id, "role": "member"},
            format="json",
        )
        row = WorkspaceMember.objects.get(user=self.other, workspace_id=ws_id)
        resp = self.client.patch(
            f"{MEMBERS_URL}{row.id}/", {"role": "admin"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        row.refresh_from_db()
        self.assertEqual(row.role, WorkspaceMember.Role.ADMIN)

    # --- duplicate membership (model unique_together) ---

    def test_cannot_add_same_member_twice(self):
        ws_id = self._create_workspace(self.owner)
        self.client.force_authenticate(self.owner)
        payload = {"user": self.other.id, "workspace": ws_id, "role": "member"}
        first = self.client.post(MEMBERS_URL, payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        second = self.client.post(MEMBERS_URL, payload, format="json")
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    # --- members list scoping (get_queryset) ---

    def test_members_list_scoped_to_my_workspaces(self):
        ws_id = self._create_workspace(self.owner)
        self.client.force_authenticate(self.owner)
        self.client.post(
            MEMBERS_URL,
            {"user": self.other.id, "workspace": ws_id, "role": "member"},
            format="json",
        )
        # a separate workspace the owner has no part in
        outsider = make_user("stranger@example.com")
        foreign = Workspace.objects.create(name="Foreign", created_by=outsider)
        WorkspaceMember.objects.create(
            user=outsider, workspace=foreign, role=WorkspaceMember.Role.OWNER
        )

        resp = self.client.get(MEMBERS_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ws_ids = {m["workspace"] for m in resp.data}
        self.assertIn(ws_id, ws_ids)
        self.assertNotIn(foreign.id, ws_ids)


class WorkspaceObjectPermissionGapTests(APITestCase):
    """Documents the CURRENT behavior of WorkspaceViewSet, which only uses
    [IsAuthenticated]. A plain member can edit/delete the whole workspace.
    These tests FAIL once an owner-only object permission is added -- update
    them then."""

    def setUp(self):
        self.owner = make_user("owner2@example.com")
        self.member = make_user("member2@example.com")
        self.client.force_authenticate(self.owner)
        ws = self.client.post(WORKSPACES_URL, {"name": "WS"}, format="json")
        self.ws_id = ws.data["id"]
        self.client.post(
            MEMBERS_URL,
            {"user": self.member.id, "workspace": self.ws_id, "role": "member"},
            format="json",
        )

    def test_plain_member_cannot_delete_workspace(self):
        self.client.force_authenticate(self.member)
        resp = self.client.delete(f"{WORKSPACES_URL}{self.ws_id}/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_plain_member_cannot_edit_workspace(self):
        self.client.force_authenticate(self.member)
        resp = self.client.patch(
            f"{WORKSPACES_URL}{self.ws_id}/", {"name": "Hacked"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_edit_workspace(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.patch(
            f"{WORKSPACES_URL}{self.ws_id}/", {"name": "Renamed"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_owner_can_delete_workspace(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.delete(f"{WORKSPACES_URL}{self.ws_id}/")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
