from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Issue
from .serializers import IssueSerializer
from .permissions import CanManageIssue


class IssueViewSet(viewsets.ModelViewSet):
    serializer_class = IssueSerializer
    permission_classes = [IsAuthenticated, CanManageIssue]

    def get_queryset(self):
        # Only issues in projects in workspaces the requester belongs to.
        return Issue.objects.filter(
            project__workspace__memberships__user=self.request.user
        )
