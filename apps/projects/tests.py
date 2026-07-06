from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.workspaces.models import Workspace, WorkspaceMember
from .models import Project

User = get_user_model()

PROJECTS_URL = "/api/projects/"


def make_user(email):
    return User.objects.create_user(
        email=email, password="supersecret123", first_name="T", last_name="U"
    )


def make_workspace(name, owner):
    ws = Workspace.objects.create(name=name, created_by=owner)
    WorkspaceMember.objects.create(
        user=owner, workspace=ws, role=WorkspaceMember.Role.OWNER
    )
    return ws


def add_member(ws, user, role):
    return WorkspaceMember.objects.create(user=user, workspace=ws, role=role)


class ProjectTests(APITestCase):
    def setUp(self):
        self.owner = make_user("p_owner@example.com")
        self.admin = make_user("p_admin@example.com")
        self.member = make_user("p_member@example.com")
        self.outsider = make_user("p_outsider@example.com")

        self.ws = make_workspace("Team", self.owner)
        add_member(self.ws, self.admin, WorkspaceMember.Role.ADMIN)
        add_member(self.ws, self.member, WorkspaceMember.Role.MEMBER)

    def _make_project(self, name="P", workspace=None):
        return Project.objects.create(
            name=name,
            workspace=workspace or self.ws,
            created_by=self.owner,
        )

    # --- create ---

    def test_create_requires_auth(self):
        resp = self.client.post(
            PROJECTS_URL, {"name": "X", "workspace": self.ws.id}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_owner_can_create_project(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.post(
            PROJECTS_URL, {"name": "Alpha", "workspace": self.ws.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Project.objects.filter(name="Alpha").exists())

    def test_admin_can_create_project(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            PROJECTS_URL, {"name": "Beta", "workspace": self.ws.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_member_cannot_create_project(self):
        self.client.force_authenticate(self.member)
        resp = self.client.post(
            PROJECTS_URL, {"name": "Nope", "workspace": self.ws.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Project.objects.filter(name="Nope").exists())

    def test_outsider_cannot_create_project(self):
        self.client.force_authenticate(self.outsider)
        resp = self.client.post(
            PROJECTS_URL, {"name": "Nope", "workspace": self.ws.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_without_workspace_returns_400_not_403(self):
        """Missing workspace is a bad request, not a permission error."""
        self.client.force_authenticate(self.owner)
        resp = self.client.post(PROJECTS_URL, {"name": "NoWs"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("workspace", resp.data)

    def test_create_sets_created_by_to_requester(self):
        """created_by is server-set to the requester, not client-controlled."""
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            PROJECTS_URL,
            {"name": "Gamma", "workspace": self.ws.id,
             "created_by": self.member.id},  # attempt to spoof
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        project = Project.objects.get(name="Gamma")
        self.assertEqual(project.created_by, self.admin)

    # --- read scoping ---

    def test_list_only_shows_projects_in_my_workspaces(self):
        self._make_project("Mine")
        # a workspace the users above have nothing to do with
        stranger = make_user("stranger@example.com")
        foreign_ws = make_workspace("Foreign", stranger)
        Project.objects.create(
            name="Foreign", workspace=foreign_ws, created_by=stranger
        )

        self.client.force_authenticate(self.member)
        resp = self.client.get(PROJECTS_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        names = [p["name"] for p in resp.data]
        self.assertIn("Mine", names)
        self.assertNotIn("Foreign", names)

    def test_member_can_retrieve_project(self):
        project = self._make_project()
        self.client.force_authenticate(self.member)
        resp = self.client.get(f"{PROJECTS_URL}{project.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_cannot_retrieve_project_in_other_workspace(self):
        stranger = make_user("stranger2@example.com")
        foreign_ws = make_workspace("Foreign", stranger)
        project = Project.objects.create(
            name="Secret", workspace=foreign_ws, created_by=stranger
        )
        self.client.force_authenticate(self.member)
        resp = self.client.get(f"{PROJECTS_URL}{project.id}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # --- edit ---

    def test_owner_can_edit_project(self):
        project = self._make_project()
        self.client.force_authenticate(self.owner)
        resp = self.client.patch(
            f"{PROJECTS_URL}{project.id}/", {"name": "Renamed"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        project.refresh_from_db()
        self.assertEqual(project.name, "Renamed")

    def test_admin_can_edit_project(self):
        project = self._make_project()
        self.client.force_authenticate(self.admin)
        resp = self.client.patch(
            f"{PROJECTS_URL}{project.id}/", {"name": "AdminEdit"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_member_cannot_edit_project(self):
        project = self._make_project()
        self.client.force_authenticate(self.member)
        resp = self.client.patch(
            f"{PROJECTS_URL}{project.id}/", {"name": "Hacked"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_workspace_is_read_only_on_update(self):
        """A project can't be moved to another workspace after creation."""
        project = self._make_project()
        other_ws = make_workspace("Other", self.owner)
        self.client.force_authenticate(self.owner)
        resp = self.client.patch(
            f"{PROJECTS_URL}{project.id}/",
            {"name": "Moved?", "workspace": other_ws.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        project.refresh_from_db()
        self.assertEqual(project.workspace_id, self.ws.id)  # unchanged
        self.assertEqual(project.name, "Moved?")            # name still applied

    # --- delete ---

    def test_owner_can_delete_project(self):
        project = self._make_project()
        self.client.force_authenticate(self.owner)
        resp = self.client.delete(f"{PROJECTS_URL}{project.id}/")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Project.objects.filter(id=project.id).exists())

    def test_admin_cannot_delete_project(self):
        """Only an OWNER may delete a project."""
        project = self._make_project()
        self.client.force_authenticate(self.admin)
        resp = self.client.delete(f"{PROJECTS_URL}{project.id}/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Project.objects.filter(id=project.id).exists())

    def test_member_cannot_delete_project(self):
        project = self._make_project()
        self.client.force_authenticate(self.member)
        resp = self.client.delete(f"{PROJECTS_URL}{project.id}/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
