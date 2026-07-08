from rest_framework import serializers

from apps.workspaces.models import WorkspaceMember
from .models import Issue, Comment


class IssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Issue
        fields = [
            "id", "title", "description", "project", "issue_type",
            "status", "priority", "assignee", "created_by",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # An issue can't be moved to another project after creation (same rule
        # projects use for their workspace). It's writable only on create.
        if self.instance is not None:
            self.fields["project"].read_only = True

    def validate(self, attrs):
        # The assignee must belong to the SAME workspace as the issue's project.
        # You can't assign work to someone who isn't on the team.
        # On update the project is locked, so fall back to the existing one.
        project = attrs.get("project") or (
            self.instance.project if self.instance else None
        )
        assignee = attrs.get("assignee")
        if assignee is not None and project is not None:
            in_workspace = WorkspaceMember.objects.filter(
                workspace=project.workspace,
                user=assignee,
            ).exists()
            if not in_workspace:
                raise serializers.ValidationError(
                    {"assignee":
                        "Assignee must be a member of the project's workspace."}
                )
        return attrs

    def create(self, validated_data):
        # The reporter is always the requester; a client-sent created_by is
        # ignored (it's read-only above).
        user = self.context["request"].user
        return Issue.objects.create(created_by=user, **validated_data)


class CommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ["id", "issue", "author", "body", "created_at", "updated_at"]
        read_only_fields = ["id", "author", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A comment can't be moved to another issue after creation.
        if self.instance is not None:
            self.fields["issue"].read_only = True

    def create(self, validated_data):
        # The author is always the requester; a client-sent author is ignored.
        user = self.context["request"].user
        return Comment.objects.create(author=user, **validated_data)
