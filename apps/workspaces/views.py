from django.shortcuts import render
from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets
from apps.workspaces.permissions import IsWorkspaceOwner, IsWorkspace
from .models import Workspace, WorkspaceMember
from .serializers import WorkspaceSerializer, WorkspaceMemberSerializer

# Create your views here.


class WorkspaceViewSet(viewsets.ModelViewSet):

    queryset = Workspace.objects.all()
    serializer_class = WorkspaceSerializer
    permission_classes = [IsAuthenticated, IsWorkspace]
    search_fields = ["name", "description"]       # ?search=
    ordering_fields = ["created_at", "updated_at", "name"]

    def get_queryset(self):
        return Workspace.objects.filter(memberships__user=self.request.user)


class WorkspaceMemberViewSet(viewsets.ModelViewSet):
    queryset = WorkspaceMember.objects.all()
    serializer_class = WorkspaceMemberSerializer
    permission_classes = [IsAuthenticated, IsWorkspaceOwner]
    filterset_fields = ["workspace", "role", "user"]   # ?workspace=&role=
    ordering_fields = ["joined_at"]

    def get_queryset(self):
        return WorkspaceMember.objects.filter(workspace__memberships__user=self.request.user)
    # الفكرة هون واحدة واحدة بدنا كل المستخدمين وين المستخدم لهاد مكان العمل هو اللي بعت الطلب عالمتصفح ال ايه بي اي
