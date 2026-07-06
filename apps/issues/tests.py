from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.workspaces.models import Workspace, WorkspaceMember
from apps.projects.models import Project
from .models import Issue

User = get_user_model()

ISSUES_URL = "/api/issues/"


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


class IssueTests(APITestCase):
    def setUp(self):
        self.owner = make_user("i_owner@example.com")
        self.admin = make_user("i_admin@example.com")
        self.member = make_user("i_member@example.com")
        self.member2 = make_user("i_member2@example.com")
        self.outsider = make_user("i_outsider@example.com")

        self.ws = make_workspace("Team", self.owner)
        add_member(self.ws, self.admin, WorkspaceMember.Role.ADMIN)
        add_member(self.ws, self.member, WorkspaceMember.Role.MEMBER)
        add_member(self.ws, self.member2, WorkspaceMember.Role.MEMBER)

        self.project = Project.objects.create(
            name="P", workspace=self.ws, created_by=self.owner
        )

    def _make_issue(self, reporter=None, assignee=None, title="Bug",
                    project=None):
        return Issue.objects.create(
            title=title,
            project=project or self.project,
            created_by=reporter or self.member,
            assignee=assignee,
        )

    # --- create ---

    def test_create_requires_auth(self):
        resp = self.client.post(
            ISSUES_URL, {"title": "X", "project": self.project.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_owner_can_create_issue(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.post(
            ISSUES_URL, {"title": "Alpha", "project": self.project.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_admin_can_create_issue(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            ISSUES_URL, {"title": "Beta", "project": self.project.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_member_can_create_issue(self):
        """Any workspace member may file an issue (Jira-style)."""
        self.client.force_authenticate(self.member)
        resp = self.client.post(
            ISSUES_URL, {"title": "Gamma", "project": self.project.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_outsider_cannot_create_issue(self):
        self.client.force_authenticate(self.outsider)
        resp = self.client.post(
            ISSUES_URL, {"title": "Nope", "project": self.project.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Issue.objects.filter(title="Nope").exists())

    def test_create_without_project_returns_400_not_403(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.post(ISSUES_URL, {"title": "NoProj"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("project", resp.data)

    def test_create_sets_created_by_to_requester(self):
        """created_by (reporter) is server-set; spoofing is ignored."""
        self.client.force_authenticate(self.member)
        resp = self.client.post(
            ISSUES_URL,
            {"title": "Spoof", "project": self.project.id,
             "created_by": self.owner.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        issue = Issue.objects.get(title="Spoof")
        self.assertEqual(issue.created_by, self.member)

    def test_create_with_assignee_in_workspace(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.post(
            ISSUES_URL,
            {"title": "Assigned", "project": self.project.id,
             "assignee": self.member.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        issue = Issue.objects.get(title="Assigned")
        self.assertEqual(issue.assignee, self.member)

    def test_cannot_assign_to_non_workspace_member(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.post(
            ISSUES_URL,
            {"title": "BadAssign", "project": self.project.id,
             "assignee": self.outsider.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("assignee", resp.data)

    def test_create_defaults(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.post(
            ISSUES_URL, {"title": "Defaults", "project": self.project.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        issue = Issue.objects.get(title="Defaults")
        self.assertEqual(issue.status, Issue.Status.TODO)
        self.assertEqual(issue.priority, Issue.Priority.MEDIUM)
        self.assertEqual(issue.issue_type, Issue.Type.TASK)

    # --- read scoping ---

    def test_list_only_shows_issues_in_my_workspaces(self):
        self._make_issue(title="Mine")
        stranger = make_user("i_stranger@example.com")
        foreign_ws = make_workspace("Foreign", stranger)
        foreign_project = Project.objects.create(
            name="FP", workspace=foreign_ws, created_by=stranger
        )
        Issue.objects.create(
            title="Foreign", project=foreign_project, created_by=stranger
        )

        self.client.force_authenticate(self.member)
        resp = self.client.get(ISSUES_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        titles = [i["title"] for i in resp.data]
        self.assertIn("Mine", titles)
        self.assertNotIn("Foreign", titles)

    def test_member_can_retrieve_issue(self):
        issue = self._make_issue()
        self.client.force_authenticate(self.member)
        resp = self.client.get(f"{ISSUES_URL}{issue.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_cannot_retrieve_issue_in_other_workspace(self):
        stranger = make_user("i_stranger2@example.com")
        foreign_ws = make_workspace("Foreign", stranger)
        foreign_project = Project.objects.create(
            name="FP", workspace=foreign_ws, created_by=stranger
        )
        issue = Issue.objects.create(
            title="Secret", project=foreign_project, created_by=stranger
        )
        self.client.force_authenticate(self.member)
        resp = self.client.get(f"{ISSUES_URL}{issue.id}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # --- edit ---

    def test_owner_can_edit_any_issue(self):
        issue = self._make_issue(reporter=self.member)
        self.client.force_authenticate(self.owner)
        resp = self.client.patch(
            f"{ISSUES_URL}{issue.id}/", {"status": Issue.Status.DONE},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        issue.refresh_from_db()
        self.assertEqual(issue.status, Issue.Status.DONE)

    def test_admin_can_edit_any_issue(self):
        issue = self._make_issue(reporter=self.member)
        self.client.force_authenticate(self.admin)
        resp = self.client.patch(
            f"{ISSUES_URL}{issue.id}/", {"priority": Issue.Priority.HIGH},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_reporter_can_edit_own_issue(self):
        issue = self._make_issue(reporter=self.member)
        self.client.force_authenticate(self.member)
        resp = self.client.patch(
            f"{ISSUES_URL}{issue.id}/", {"title": "Edited"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_assignee_can_edit_assigned_issue(self):
        issue = self._make_issue(reporter=self.member, assignee=self.member2)
        self.client.force_authenticate(self.member2)
        resp = self.client.patch(
            f"{ISSUES_URL}{issue.id}/", {"status": Issue.Status.IN_PROGRESS},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_uninvolved_member_cannot_edit_issue(self):
        """A member who is neither reporter nor assignee can't edit."""
        issue = self._make_issue(reporter=self.member, assignee=self.member)
        self.client.force_authenticate(self.member2)
        resp = self.client.patch(
            f"{ISSUES_URL}{issue.id}/", {"title": "Hacked"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_outsider_cannot_edit_issue(self):
        issue = self._make_issue()
        self.client.force_authenticate(self.outsider)
        resp = self.client.patch(
            f"{ISSUES_URL}{issue.id}/", {"title": "Hacked"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_project_is_read_only_on_update(self):
        """An issue can't be moved to another project after creation."""
        issue = self._make_issue(reporter=self.member)
        other_project = Project.objects.create(
            name="Other", workspace=self.ws, created_by=self.owner
        )
        self.client.force_authenticate(self.owner)
        resp = self.client.patch(
            f"{ISSUES_URL}{issue.id}/",
            {"title": "Moved?", "project": other_project.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        issue.refresh_from_db()
        self.assertEqual(issue.project_id, self.project.id)  # unchanged
        self.assertEqual(issue.title, "Moved?")

    # --- reassignment ---

    def test_owner_can_reassign_issue(self):
        issue = self._make_issue(reporter=self.member, assignee=self.member)
        self.client.force_authenticate(self.owner)
        resp = self.client.patch(
            f"{ISSUES_URL}{issue.id}/", {"assignee": self.member2.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        issue.refresh_from_db()
        self.assertEqual(issue.assignee, self.member2)

    def test_reporter_can_reassign_issue(self):
        issue = self._make_issue(reporter=self.member, assignee=self.member)
        self.client.force_authenticate(self.member)
        resp = self.client.patch(
            f"{ISSUES_URL}{issue.id}/", {"assignee": self.member2.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        issue.refresh_from_db()
        self.assertEqual(issue.assignee, self.member2)

    def test_assignee_cannot_reassign_issue(self):
        """An assignee can work the issue but can't hand it off to someone else."""
        issue = self._make_issue(reporter=self.member, assignee=self.member2)
        self.client.force_authenticate(self.member2)
        resp = self.client.patch(
            f"{ISSUES_URL}{issue.id}/", {"assignee": self.member.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        issue.refresh_from_db()
        self.assertEqual(issue.assignee, self.member2)  # unchanged

    def test_assignee_can_edit_while_keeping_same_assignee(self):
        """Sending the unchanged assignee value shouldn't trip the guard."""
        issue = self._make_issue(reporter=self.member, assignee=self.member2)
        self.client.force_authenticate(self.member2)
        resp = self.client.patch(
            f"{ISSUES_URL}{issue.id}/",
            {"status": Issue.Status.IN_REVIEW, "assignee": self.member2.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    # --- delete ---

    def test_owner_can_delete_issue(self):
        issue = self._make_issue(reporter=self.member)
        self.client.force_authenticate(self.owner)
        resp = self.client.delete(f"{ISSUES_URL}{issue.id}/")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Issue.objects.filter(id=issue.id).exists())

    def test_admin_can_delete_issue(self):
        issue = self._make_issue(reporter=self.member)
        self.client.force_authenticate(self.admin)
        resp = self.client.delete(f"{ISSUES_URL}{issue.id}/")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    def test_reporter_can_delete_own_issue(self):
        issue = self._make_issue(reporter=self.member)
        self.client.force_authenticate(self.member)
        resp = self.client.delete(f"{ISSUES_URL}{issue.id}/")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    def test_assignee_cannot_delete_issue(self):
        """An assignee who isn't the reporter can't delete the issue."""
        issue = self._make_issue(reporter=self.member, assignee=self.member2)
        self.client.force_authenticate(self.member2)
        resp = self.client.delete(f"{ISSUES_URL}{issue.id}/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Issue.objects.filter(id=issue.id).exists())

    def test_uninvolved_member_cannot_delete_issue(self):
        issue = self._make_issue(reporter=self.member)
        self.client.force_authenticate(self.member2)
        resp = self.client.delete(f"{ISSUES_URL}{issue.id}/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
