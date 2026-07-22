import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.workspaces.models import Workspace, WorkspaceMember
from apps.projects.models import Project
from .models import Issue, Comment, Attachment

User = get_user_model()

ISSUES_URL = "/api/issues/"
COMMENTS_URL = "/api/comments/"
ATTACHMENTS_URL = "/api/attachments/"


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
        titles = [i["title"] for i in resp.data["results"]]
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


class CommentTests(APITestCase):
    def setUp(self):
        self.owner = make_user("c_owner@example.com")
        self.admin = make_user("c_admin@example.com")
        self.member = make_user("c_member@example.com")
        self.member2 = make_user("c_member2@example.com")
        self.outsider = make_user("c_outsider@example.com")

        self.ws = make_workspace("Team", self.owner)
        add_member(self.ws, self.admin, WorkspaceMember.Role.ADMIN)
        add_member(self.ws, self.member, WorkspaceMember.Role.MEMBER)
        add_member(self.ws, self.member2, WorkspaceMember.Role.MEMBER)

        self.project = Project.objects.create(
            name="P", workspace=self.ws, created_by=self.owner
        )
        self.issue = Issue.objects.create(
            title="Bug", project=self.project, created_by=self.member
        )

    def _make_comment(self, author=None, body="hi", issue=None):
        return Comment.objects.create(
            issue=issue or self.issue,
            author=author or self.member,
            body=body,
        )

    # --- create ---

    def test_create_requires_auth(self):
        resp = self.client.post(
            COMMENTS_URL, {"issue": self.issue.id, "body": "x"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_member_can_comment(self):
        self.client.force_authenticate(self.member2)
        resp = self.client.post(
            COMMENTS_URL, {"issue": self.issue.id, "body": "looks good"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_owner_can_comment(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.post(
            COMMENTS_URL, {"issue": self.issue.id, "body": "ship it"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_outsider_cannot_comment(self):
        self.client.force_authenticate(self.outsider)
        resp = self.client.post(
            COMMENTS_URL, {"issue": self.issue.id, "body": "nope"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_without_issue_returns_400_not_403(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.post(COMMENTS_URL, {"body": "orphan"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("issue", resp.data)

    def test_create_sets_author_to_requester(self):
        self.client.force_authenticate(self.member2)
        resp = self.client.post(
            COMMENTS_URL,
            {"issue": self.issue.id, "body": "spoof", "author": self.owner.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        comment = Comment.objects.get(body="spoof")
        self.assertEqual(comment.author, self.member2)

    # --- read scoping ---

    def test_list_only_shows_comments_in_my_workspaces(self):
        self._make_comment(body="Mine")
        stranger = make_user("c_stranger@example.com")
        foreign_ws = make_workspace("Foreign", stranger)
        foreign_project = Project.objects.create(
            name="FP", workspace=foreign_ws, created_by=stranger
        )
        foreign_issue = Issue.objects.create(
            title="FI", project=foreign_project, created_by=stranger
        )
        Comment.objects.create(
            issue=foreign_issue, author=stranger, body="Foreign"
        )

        self.client.force_authenticate(self.member)
        resp = self.client.get(COMMENTS_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        bodies = [c["body"] for c in resp.data["results"]]
        self.assertIn("Mine", bodies)
        self.assertNotIn("Foreign", bodies)

    def test_cannot_retrieve_comment_in_other_workspace(self):
        stranger = make_user("c_stranger2@example.com")
        foreign_ws = make_workspace("Foreign", stranger)
        foreign_project = Project.objects.create(
            name="FP", workspace=foreign_ws, created_by=stranger
        )
        foreign_issue = Issue.objects.create(
            title="FI", project=foreign_project, created_by=stranger
        )
        comment = Comment.objects.create(
            issue=foreign_issue, author=stranger, body="secret"
        )
        self.client.force_authenticate(self.member)
        resp = self.client.get(f"{COMMENTS_URL}{comment.id}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # --- edit ---

    def test_author_can_edit_own_comment(self):
        comment = self._make_comment(author=self.member)
        self.client.force_authenticate(self.member)
        resp = self.client.patch(
            f"{COMMENTS_URL}{comment.id}/", {"body": "edited"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        comment.refresh_from_db()
        self.assertEqual(comment.body, "edited")

    def test_owner_cannot_edit_others_comment(self):
        """Nobody rewrites someone else's words - even an owner."""
        comment = self._make_comment(author=self.member)
        self.client.force_authenticate(self.owner)
        resp = self.client.patch(
            f"{COMMENTS_URL}{comment.id}/", {"body": "tampered"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_other_member_cannot_edit_comment(self):
        comment = self._make_comment(author=self.member)
        self.client.force_authenticate(self.member2)
        resp = self.client.patch(
            f"{COMMENTS_URL}{comment.id}/", {"body": "tampered"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_issue_is_read_only_on_update(self):
        comment = self._make_comment(author=self.member)
        other_issue = Issue.objects.create(
            title="Other", project=self.project, created_by=self.owner
        )
        self.client.force_authenticate(self.member)
        resp = self.client.patch(
            f"{COMMENTS_URL}{comment.id}/",
            {"body": "moved?", "issue": other_issue.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        comment.refresh_from_db()
        self.assertEqual(comment.issue_id, self.issue.id)  # unchanged

    # --- delete ---

    def test_author_can_delete_own_comment(self):
        comment = self._make_comment(author=self.member)
        self.client.force_authenticate(self.member)
        resp = self.client.delete(f"{COMMENTS_URL}{comment.id}/")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    def test_owner_can_delete_others_comment(self):
        """Managers may moderate (delete) any comment."""
        comment = self._make_comment(author=self.member)
        self.client.force_authenticate(self.owner)
        resp = self.client.delete(f"{COMMENTS_URL}{comment.id}/")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    def test_admin_can_delete_others_comment(self):
        comment = self._make_comment(author=self.member)
        self.client.force_authenticate(self.admin)
        resp = self.client.delete(f"{COMMENTS_URL}{comment.id}/")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    def test_member_cannot_delete_others_comment(self):
        comment = self._make_comment(author=self.member)
        self.client.force_authenticate(self.member2)
        resp = self.client.delete(f"{COMMENTS_URL}{comment.id}/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Comment.objects.filter(id=comment.id).exists())


class IssueFilterSearchPaginationTests(APITestCase):
    def setUp(self):
        self.owner = make_user("f_owner@example.com")
        self.dev = make_user("f_dev@example.com")
        self.ws = make_workspace("Team", self.owner)
        add_member(self.ws, self.dev, WorkspaceMember.Role.MEMBER)
        self.project = Project.objects.create(
            name="P", workspace=self.ws, created_by=self.owner
        )
        self.client.force_authenticate(self.owner)

    def _issue(self, **kwargs):
        defaults = dict(
            title="I", project=self.project, created_by=self.owner
        )
        defaults.update(kwargs)
        return Issue.objects.create(**defaults)

    # --- pagination ---

    def test_list_is_paginated(self):
        for n in range(25):
            self._issue(title=f"Issue {n}")
        resp = self.client.get(ISSUES_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Paged envelope, not a bare list.
        self.assertIn("count", resp.data)
        self.assertIn("results", resp.data)
        self.assertEqual(resp.data["count"], 25)
        self.assertEqual(len(resp.data["results"]), 20)   # PAGE_SIZE
        self.assertIsNotNone(resp.data["next"])

    def test_second_page(self):
        for n in range(25):
            self._issue(title=f"Issue {n}")
        resp = self.client.get(ISSUES_URL + "?page=2")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["results"]), 5)    # 25 - 20

    # --- filtering ---

    def test_filter_by_status(self):
        self._issue(title="Open", status=Issue.Status.TODO)
        self._issue(title="Closed", status=Issue.Status.DONE)
        resp = self.client.get(ISSUES_URL + f"?status={Issue.Status.DONE}")
        titles = [i["title"] for i in resp.data["results"]]
        self.assertEqual(titles, ["Closed"])

    def test_filter_by_priority(self):
        self._issue(title="Hot", priority=Issue.Priority.CRITICAL)
        self._issue(title="Cold", priority=Issue.Priority.LOW)
        resp = self.client.get(
            ISSUES_URL + f"?priority={Issue.Priority.CRITICAL}"
        )
        titles = [i["title"] for i in resp.data["results"]]
        self.assertEqual(titles, ["Hot"])

    def test_filter_by_assignee(self):
        self._issue(title="Assigned", assignee=self.dev)
        self._issue(title="Unassigned")
        resp = self.client.get(ISSUES_URL + f"?assignee={self.dev.id}")
        titles = [i["title"] for i in resp.data["results"]]
        self.assertEqual(titles, ["Assigned"])

    def test_filter_combined(self):
        self._issue(title="Match", status=Issue.Status.TODO,
                    priority=Issue.Priority.HIGH)
        self._issue(title="WrongPriority", status=Issue.Status.TODO,
                    priority=Issue.Priority.LOW)
        self._issue(title="WrongStatus", status=Issue.Status.DONE,
                    priority=Issue.Priority.HIGH)
        resp = self.client.get(
            ISSUES_URL
            + f"?status={Issue.Status.TODO}&priority={Issue.Priority.HIGH}"
        )
        titles = [i["title"] for i in resp.data["results"]]
        self.assertEqual(titles, ["Match"])

    # --- search ---

    def test_search_matches_title(self):
        self._issue(title="Login button broken")
        self._issue(title="Signup page slow")
        resp = self.client.get(ISSUES_URL + "?search=login")
        titles = [i["title"] for i in resp.data["results"]]
        self.assertEqual(titles, ["Login button broken"])

    def test_search_matches_description(self):
        self._issue(title="A", description="crashes on submit")
        self._issue(title="B", description="all good")
        resp = self.client.get(ISSUES_URL + "?search=crashes")
        titles = [i["title"] for i in resp.data["results"]]
        self.assertEqual(titles, ["A"])

    # --- ordering ---

    def test_ordering_by_created_at_ascending(self):
        first = self._issue(title="First")
        second = self._issue(title="Second")
        resp = self.client.get(ISSUES_URL + "?ordering=created_at")
        ids = [i["id"] for i in resp.data["results"]]
        self.assertEqual(ids, [first.id, second.id])

    # --- comments filter ---

    def test_filter_comments_by_issue(self):
        issue_a = self._issue(title="A")
        issue_b = self._issue(title="B")
        Comment.objects.create(issue=issue_a, author=self.owner, body="on A")
        Comment.objects.create(issue=issue_b, author=self.owner, body="on B")
        resp = self.client.get(COMMENTS_URL + f"?issue={issue_a.id}")
        bodies = [c["body"] for c in resp.data["results"]]
        self.assertEqual(bodies, ["on A"])


_TEMP_MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=_TEMP_MEDIA)
class AttachmentTests(APITestCase):
    """File uploads on issues.

    Matrix (attachments: /api/attachments/<id>/):
      action | manager | uploader | other member | outsider
      view   |  yes    |  yes     | yes          | no (404, scoped out)
      create |  yes    |   -      | yes          | no (403)
      edit   |  yes    |  yes     | no           | no
      delete |  yes    |  yes     | no           | no
    """

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_TEMP_MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.owner = make_user("a_owner@example.com")
        self.admin = make_user("a_admin@example.com")
        self.member = make_user("a_member@example.com")
        self.member2 = make_user("a_member2@example.com")
        self.outsider = make_user("a_outsider@example.com")

        self.ws = make_workspace("Team", self.owner)
        add_member(self.ws, self.admin, WorkspaceMember.Role.ADMIN)
        add_member(self.ws, self.member, WorkspaceMember.Role.MEMBER)
        add_member(self.ws, self.member2, WorkspaceMember.Role.MEMBER)

        self.project = Project.objects.create(
            name="P", workspace=self.ws, created_by=self.owner
        )
        self.issue = Issue.objects.create(
            title="Bug", project=self.project, created_by=self.member
        )

    def _upload_file(self, name="log.txt", content=b"data"):
        return SimpleUploadedFile(name, content, content_type="text/plain")

    def _make_attachment(self, uploader=None):
        return Attachment.objects.create(
            issue=self.issue,
            file=self._upload_file(),
            uploaded_by=uploader or self.member,
        )

    # --- create ---

    def test_create_requires_auth(self):
        resp = self.client.post(
            ATTACHMENTS_URL,
            {"issue": self.issue.id, "file": self._upload_file()},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_member_can_upload(self):
        """Any workspace member may upload a file to an issue."""
        self.client.force_authenticate(self.member2)
        resp = self.client.post(
            ATTACHMENTS_URL,
            {"issue": self.issue.id, "file": self._upload_file()},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # uploaded_by is server-set to the requester, not spoofable.
        att = Attachment.objects.get(id=resp.data["id"])
        self.assertEqual(att.uploaded_by, self.member2)

    def test_uploaded_by_is_server_set(self):
        self.client.force_authenticate(self.member2)
        resp = self.client.post(
            ATTACHMENTS_URL,
            {
                "issue": self.issue.id,
                "file": self._upload_file(),
                "uploaded_by": self.owner.id,  # spoof attempt, ignored
            },
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        att = Attachment.objects.get(id=resp.data["id"])
        self.assertEqual(att.uploaded_by, self.member2)

    def test_outsider_cannot_upload(self):
        self.client.force_authenticate(self.outsider)
        resp = self.client.post(
            ATTACHMENTS_URL,
            {"issue": self.issue.id, "file": self._upload_file()},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_upload_without_issue_returns_400(self):
        """Missing required `issue` is a validation problem -> 400, not 403."""
        self.client.force_authenticate(self.member)
        resp = self.client.post(
            ATTACHMENTS_URL,
            {"file": self._upload_file()},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("issue", resp.data)

    def test_upload_without_file_returns_400(self):
        self.client.force_authenticate(self.member)
        resp = self.client.post(
            ATTACHMENTS_URL,
            {"issue": self.issue.id},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", resp.data)

    # --- view / scoping ---

    def test_list_scoped_to_my_workspaces(self):
        self._make_attachment(uploader=self.member)
        self.client.force_authenticate(self.member)
        resp = self.client.get(ATTACHMENTS_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)

    def test_outsider_cannot_see_attachment(self):
        att = self._make_attachment()
        self.client.force_authenticate(self.outsider)
        resp = self.client.get(f"{ATTACHMENTS_URL}{att.id}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_member_can_view_attachment(self):
        att = self._make_attachment()
        self.client.force_authenticate(self.member2)
        resp = self.client.get(f"{ATTACHMENTS_URL}{att.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["filename"], "log.txt")

    # --- delete ---

    def test_uploader_can_delete(self):
        att = self._make_attachment(uploader=self.member)
        stored_path = att.file.path
        self.client.force_authenticate(self.member)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.delete(f"{ATTACHMENTS_URL}{att.id}/")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(att.file.storage.exists(stored_path))

    def test_manager_can_delete_others_attachment(self):
        att = self._make_attachment(uploader=self.member)
        self.client.force_authenticate(self.admin)
        resp = self.client.delete(f"{ATTACHMENTS_URL}{att.id}/")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    def test_other_member_cannot_delete(self):
        att = self._make_attachment(uploader=self.member)
        self.client.force_authenticate(self.member2)
        resp = self.client.delete(f"{ATTACHMENTS_URL}{att.id}/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # --- edit ---

    def test_other_member_cannot_replace_file(self):
        att = self._make_attachment(uploader=self.member)
        self.client.force_authenticate(self.member2)
        resp = self.client.patch(
            f"{ATTACHMENTS_URL}{att.id}/",
            {"file": self._upload_file(name="new.txt")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_replacing_file_deletes_previous_file(self):
        att = self._make_attachment(uploader=self.member)
        old_name = att.file.name
        self.client.force_authenticate(self.member)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.patch(
                f"{ATTACHMENTS_URL}{att.id}/",
                {"file": self._upload_file(name="new.txt")},
                format="multipart",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        att.refresh_from_db()
        self.assertFalse(att.file.storage.exists(old_name))
        self.assertTrue(att.file.storage.exists(att.file.name))

    def test_cascade_delete_removes_file(self):
        att = self._make_attachment(uploader=self.member)
        stored_name = att.file.name
        with self.captureOnCommitCallbacks(execute=True):
            self.issue.delete()
        self.assertFalse(att.file.storage.exists(stored_name))

    def test_issue_is_read_only_on_update(self):
        att = self._make_attachment(uploader=self.member)
        other_issue = Issue.objects.create(
            title="Other", project=self.project, created_by=self.member
        )
        self.client.force_authenticate(self.member)
        resp = self.client.patch(
            f"{ATTACHMENTS_URL}{att.id}/",
            {"issue": other_issue.id},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        att.refresh_from_db()
        self.assertEqual(att.issue_id, self.issue.id)  # unchanged

    # --- filter ---

    def test_filter_attachments_by_issue(self):
        issue_b = Issue.objects.create(
            title="B", project=self.project, created_by=self.member
        )
        self._make_attachment(uploader=self.member)  # on self.issue
        Attachment.objects.create(
            issue=issue_b, file=self._upload_file(), uploaded_by=self.member
        )
        self.client.force_authenticate(self.member)
        resp = self.client.get(ATTACHMENTS_URL + f"?issue={issue_b.id}")
        self.assertEqual(resp.data["count"], 1)
