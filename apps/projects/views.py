from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Project
from .serializers import ProjectSerializer
from .permissions import IsWorkspaceManager


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated, IsWorkspaceManager]
    filterset_fields = ["workspace"]              # ?workspace=
    search_fields = ["name", "description"]       # ?search=
    ordering_fields = ["created_at", "updated_at", "name"]

    def get_queryset(self):
        # Only projects in workspaces the requester belongs to.
        return Project.objects.filter(
            workspace__memberships__user=self.request.user
        )
