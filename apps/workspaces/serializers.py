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
