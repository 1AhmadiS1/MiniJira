from rest_framework import permissions
from rest_framework.permissions import BasePermission

from .models import WorkspaceMember, Workspace


class IsWorkspace(BasePermission):
    """Only a workspace member may view the workspace."""
    def has_permission(self, request, view):
        return True

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user == obj.created_by


class IsWorkspaceOwner(BasePermission):
    """Only a workspace OWNER may add/edit/delete members of that workspace."""

    def has_permission(self, request, view):
        if request.method != "POST":
            return True

        workspace_id = request.data.get("workspace")
        if not workspace_id:
            return False

        return WorkspaceMember.objects.filter(
            user=request.user,
            workspace_id=workspace_id,
            role=WorkspaceMember.Role.OWNER,
        ).exists()

    def has_object_permission(self, request, view, obj):
        # POINT 7 — guards EDIT/DELETE (PATCH/PUT/DELETE /members/<id>/).
        if request.method in permissions.SAFE_METHODS:
            return True
        if request.method == "DELETE" and obj.user == request.user:
            return True
        return WorkspaceMember.objects.filter(
            user=request.user,
            workspace=obj.workspace,
            role=WorkspaceMember.Role.OWNER,
        ).exists()



