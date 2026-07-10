from rest_framework import permissions
from rest_framework.permissions import BasePermission

from .models import WorkspaceMember, Workspace


# Role hierarchy: owner > admin > member. Used for both edit and delete rules.
RANK = {
    WorkspaceMember.Role.MEMBER: 1,
    WorkspaceMember.Role.ADMIN: 2,
    WorkspaceMember.Role.OWNER: 3,
}


class IsWorkspace(BasePermission):
    """Only a workspace member may view the workspace."""

    def has_permission(self, request, view):
        return True

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return WorkspaceMember.objects.filter(
            user=request.user,
            workspace=obj,
            role=WorkspaceMember.Role.OWNER,).exists()


class IsWorkspaceOwner(BasePermission):
    """Owners and admins manage members, constrained by the role hierarchy
    (owner > admin > member): you may only add/edit/delete someone strictly
    below your own rank."""

    def has_permission(self, request, view):
        if request.method != "POST":
            return True

        workspace_id = request.data.get("workspace")
        if not workspace_id:
            # Missing required field is a VALIDATION problem, not a permission
            # one: let the serializer raise the clean 400 instead of a 403.
            return True

        requester = WorkspaceMember.objects.filter(
            user=request.user,
            workspace_id=workspace_id,
        ).first()
        if requester is None:
            return False
        # Only owners and admins may add members.
        if requester.role not in (
            WorkspaceMember.Role.OWNER,
            WorkspaceMember.Role.ADMIN,
        ):
            return False
        # You may only add someone strictly BELOW your rank (an admin can add
        # members but not other admins; owner-on-create is blocked in the
        # serializer). Unknown roles are left for the serializer to reject (400).
        new_role = request.data.get("role") or WorkspaceMember.Role.MEMBER
        if new_role in RANK and RANK[new_role] >= RANK[requester.role]:
            return False
        return True

    def has_object_permission(self, request, view, obj):
        # POINT 7 — guards EDIT/DELETE (PATCH/PUT/DELETE /members/<id>/).
        if request.method in permissions.SAFE_METHODS:
            return True

        requester = WorkspaceMember.objects.filter(
            user=request.user,
            workspace=obj.workspace,
        ).first()
        if requester is None:
            return False

        if request.method == "DELETE":
            # An owner can only be removed by leaving themselves, and only while
            # another owner still remains (transfer / co-owner exists).
            if obj.role == WorkspaceMember.Role.OWNER:
                another_owner_exists = WorkspaceMember.objects.filter(
                    workspace=obj.workspace,
                    role=WorkspaceMember.Role.OWNER,
                ).exclude(pk=obj.pk).exists()
                return another_owner_exists and obj.user == request.user
            # Any user may remove their OWN (non-owner) membership = leave.
            if obj.user == request.user:
                return True
            # Otherwise you may only remove someone strictly BELOW your rank:
            # admins can't remove fellow admins, members can't remove anyone.
            return RANK[requester.role] > RANK[obj.role]

        # PUT/PATCH - edit a member's data. Hierarchy: owner > admin > member.
        # You may only edit someone strictly BELOW you: admins can't edit other
        # admins, owners can't edit other owners, and no one edits upward.
        if RANK[requester.role] <= RANK[obj.role]:
            return False
        # Only an OWNER may change a role; admins can edit other data only.
        new_role = request.data.get("role")
        if (new_role is not None
                and new_role != obj.role
                and requester.role != WorkspaceMember.Role.OWNER):
            return False
        return True

