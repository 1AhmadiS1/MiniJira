from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Project
from .serializers import ProjectSerializer
from .permissions import IsWorkspaceManager


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated, IsWorkspaceManager]

    def get_queryset(self):
        # Only projects in workspaces the requester belongs to.
        return Project.objects.filter(
            workspace__memberships__user=self.request.user
        )
