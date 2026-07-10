from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Issue, Comment, Attachment
from .serializers import (
    IssueSerializer, CommentSerializer, AttachmentSerializer,
)
from .permissions import (
    CanManageIssue, CanManageComment, CanManageAttachment,
)


class IssueViewSet(viewsets.ModelViewSet):
    serializer_class = IssueSerializer
    permission_classes = [IsAuthenticated, CanManageIssue]
    # ?project=&status=&priority=&issue_type=&assignee=
    filterset_fields = ["project", "status", "priority", "issue_type",
                        "assignee"]
    # ?search= matches title/description
    search_fields = ["title", "description"]
    # ?ordering= (prefix - for descending), e.g. ?ordering=-created_at
    ordering_fields = ["created_at", "updated_at", "priority", "status"]

    def get_queryset(self):
        # Only issues in projects in workspaces the requester belongs to.
        return Issue.objects.filter(
            project__workspace__memberships__user=self.request.user
        )


class CommentViewSet(viewsets.ModelViewSet):
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated, CanManageComment]
    # ?issue=&author=  (list a single issue's comment thread)
    filterset_fields = ["issue", "author"]
    search_fields = ["body"]
    ordering_fields = ["created_at", "updated_at"]

    def get_queryset(self):
        # Only comments on issues in workspaces the requester belongs to.
        return Comment.objects.filter(
            issue__project__workspace__memberships__user=self.request.user
        )


class AttachmentViewSet(viewsets.ModelViewSet):
    serializer_class = AttachmentSerializer
    permission_classes = [IsAuthenticated, CanManageAttachment]
    # ?issue=&uploaded_by=  (list one issue's files)
    filterset_fields = ["issue", "uploaded_by"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        # Only attachments on issues in workspaces the requester belongs to.
        return Attachment.objects.filter(
            issue__project__workspace__memberships__user=self.request.user
        )
