from rest_framework import serializers
from .models import Workspace, WorkspaceMember


class WorkspaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workspace
        fields = ["id", "name", "description", "created_by", "updated_at",
                  "created_at"]
        read_only_fields = ["id", "created_by", "updated_at", "created_at"]

    def create(self, validated_data):
        user = self.context['request'].user
        workspace = Workspace.objects.create(created_by=user, **validated_data)
        WorkspaceMember.objects.create(
            user=user, workspace=workspace, role=WorkspaceMember.Role.OWNER)
        return workspace


class WorkspaceMemberSerializer(serializers.ModelSerializer):

    class Meta:
        model = WorkspaceMember
        fields = ["id", "user", "workspace", "role", "joined_at"]
        read_only_fields = ["id", "joined_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # `user` and `workspace` identify the membership and must not change
        # after creation; only `role` (and future data) is editable on update.
        if self.instance is not None:
            self.fields["user"].read_only = True
            self.fields["workspace"].read_only = True

    def validate_role(self, value):
        request = self.context["request"]
        # check if the values etc.........
        if value not in [WorkspaceMember.Role.OWNER, WorkspaceMember.Role.ADMIN, WorkspaceMember.Role.MEMBER]:
            raise serializers.ValidationError("Invalid role.")
        if request.method == "POST" and value == WorkspaceMember.Role.OWNER:
            raise serializers.ValidationError(
                "Cannot assign OWNER role on creation.")
        # Option A: an owner MAY promote another member to OWNER (co-owner /
        # ownership transfer). Only demoting an existing OWNER is forbidden here;
        # to give up ownership the owner deletes their own membership (which the
        # permission layer allows only once another owner exists).
        if request.method in ["PUT", "PATCH"] and self.instance.role == WorkspaceMember.Role.OWNER:
            raise serializers.ValidationError(
                "Cannot change role of an OWNER.")
        return value
