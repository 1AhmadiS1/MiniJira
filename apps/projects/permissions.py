from rest_framework import permissions
from rest_framework.permissions import BasePermission

from apps.workspaces.models import WorkspaceMember


class IsWorkspaceManager(BasePermission):
    """Owner/admin of the workspace may create and edit its projects;
    only an OWNER may delete; any workspace member may read."""

    _MANAGER_ROLES = (WorkspaceMember.Role.OWNER, WorkspaceMember.Role.ADMIN)

    def has_permission(self, request, view):
        if request.method != "POST":
            return True
        workspace_id = request.data.get("workspace")
        if not workspace_id:
            # No workspace given: don't mask it as a 403. Let the serializer
            # raise a clear 400 "this field is required" instead.
            return True
        return WorkspaceMember.objects.filter(
            user=request.user,
            workspace_id=workspace_id,
            role__in=self._MANAGER_ROLES,
        ).exists()

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        if request.method == "DELETE":
            return WorkspaceMember.objects.filter(
                user=request.user,
                workspace=obj.workspace,
                role=WorkspaceMember.Role.OWNER,
            ).exists()
        # PUT / PATCH
        return WorkspaceMember.objects.filter(
            user=request.user,
            workspace=obj.workspace,
            role__in=self._MANAGER_ROLES,
            ).exists()
