from rest_framework import permissions
from rest_framework.permissions import BasePermission

from apps.workspaces.models import WorkspaceMember


class CanManageIssue(BasePermission):
    """Who may do what to an issue (real Jira-style rules).

    An issue lives in a Project, which lives in a Workspace. Three "hats" can
    apply to the requester, and any of them can be true at once:
      - MANAGER: workspace owner/admin of the issue's workspace -> full control.
      - REPORTER: the person who filed it (obj.created_by).
      - ASSIGNEE: the person currently doing the work (obj.assignee).

    Rules:
      - view (SAFE): any workspace member (already scoped by get_queryset).
      - create: any member of the target project's workspace may file an issue.
      - edit (PUT/PATCH): manager OR reporter OR assignee.
          * reassignment (changing `assignee`) is manager/reporter only -
            an assignee can work the issue but can't hand it off.
      - delete: manager OR reporter only (an assignee can't delete work).
    """

    _MANAGER_ROLES = (WorkspaceMember.Role.OWNER, WorkspaceMember.Role.ADMIN)

    def has_permission(self, request, view):
        if request.method != "POST":
            return True
        project_id = request.data.get("project")
        if not project_id:
            # No project given: let the serializer raise a clean 400 rather
            # than masking it as a 403.
            return True
        # Any member (owner/admin/member) of the project's workspace may create.
        return WorkspaceMember.objects.filter(
            user=request.user,
            workspace__projects__id=project_id,
        ).exists()

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        membership = WorkspaceMember.objects.filter(
            user=request.user,
            workspace=obj.project.workspace,
        ).first()
        if membership is None:
            return False  # not even in the workspace

        is_manager = membership.role in self._MANAGER_ROLES
        is_reporter = obj.created_by_id == request.user.id
        is_assignee = obj.assignee_id == request.user.id

        if request.method == "DELETE":
            # Managers or the reporter may delete; a pure assignee may not.
            return is_manager or is_reporter

        # PUT / PATCH.
        if not (is_manager or is_reporter or is_assignee):
            return False

        # Reassignment guard: only managers or the reporter may change who the
        # issue is assigned to. An assignee editing their own task can't dump it
        # on someone else.
        if "assignee" in request.data and not (is_manager or is_reporter):
            new_assignee = request.data.get("assignee")
            try:
                new_id = (int(new_assignee)
                          if new_assignee not in (None, "") else None)
            except (TypeError, ValueError):
                # Invalid value: treat as a change and let the check block it;
                # the serializer would 400 anyway.
                new_id = new_assignee
            if new_id != obj.assignee_id:
                return False
        return True


class CanManageComment(BasePermission):
    """Who may do what to a comment on an issue.

    A comment lives on an Issue -> Project -> Workspace.
      - view (SAFE): any workspace member (already scoped by get_queryset).
      - create: any member of the issue's workspace may comment.
      - edit (PUT/PATCH): the AUTHOR only - nobody rewrites someone else's words.
      - delete: the AUTHOR, or a MANAGER (workspace owner/admin) for moderation.
    """

    _MANAGER_ROLES = (WorkspaceMember.Role.OWNER, WorkspaceMember.Role.ADMIN)

    def has_permission(self, request, view):
        if request.method != "POST":
            return True
        issue_id = request.data.get("issue")
        if not issue_id:
            # No issue given: let the serializer raise a clean 400.
            return True
        # Any member of the issue's workspace may comment.
        return WorkspaceMember.objects.filter(
            user=request.user,
            workspace__projects__issues__id=issue_id,
        ).exists()

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        is_author = obj.author_id == request.user.id

        if request.method == "DELETE":
            if is_author:
                return True
            # Managers may delete others' comments (moderation).
            return WorkspaceMember.objects.filter(
                user=request.user,
                workspace=obj.issue.project.workspace,
                role__in=self._MANAGER_ROLES,
            ).exists()

        # PUT / PATCH - only the author may edit their own comment.
        return is_author


class CanManageAttachment(BasePermission):
    """Who may do what to a file attached to an issue.

    An attachment lives on an Issue -> Project -> Workspace.
      - view (SAFE): any workspace member (already scoped by get_queryset).
      - create: any member of the issue's workspace may upload.
      - edit (PUT/PATCH) / delete: the UPLOADER, or a MANAGER (workspace
        owner/admin) for moderation.
    """

    _MANAGER_ROLES = (WorkspaceMember.Role.OWNER, WorkspaceMember.Role.ADMIN)

    def has_permission(self, request, view):
        if request.method != "POST":
            return True
        issue_id = request.data.get("issue")
        if not issue_id:
            # No issue given: let the serializer raise a clean 400.
            return True
        # Any member of the issue's workspace may upload.
        return WorkspaceMember.objects.filter(
            user=request.user,
            workspace__projects__issues__id=issue_id,
        ).exists()

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        if obj.uploaded_by_id == request.user.id:
            return True
        # Managers may edit/delete others' attachments (moderation).
        return WorkspaceMember.objects.filter(
            user=request.user,
            workspace=obj.issue.project.workspace,
            role__in=self._MANAGER_ROLES,
        ).exists()
