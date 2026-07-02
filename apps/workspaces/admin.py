from django.contrib import admin

from apps.workspaces.models import Workspace, WorkspaceMember


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ["name", "created_by", "created_at","id"]
    search_fields = ["name", "created_by__email"]
    list_filter = ["created_at"]
    list_select_related = ["created_by"]
    ordering = ["-created_at"]


@admin.register(WorkspaceMember)
class WorkspaceMemberAdmin(admin.ModelAdmin):
    list_display = ["user", "workspace", "role", "joined_at", "id"]
    search_fields = ["user__email", "workspace__name", "role"]
    list_filter = ["role", "joined_at"]
    list_select_related = ["user", "workspace"]
    ordering = ["-joined_at"]