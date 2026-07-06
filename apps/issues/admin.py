from django.contrib import admin

from .models import Issue


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'issue_type', 'status', 'priority',
                    'assignee', 'created_by', 'created_at', 'updated_at')
    search_fields = ('title', 'description')
    list_filter = ('issue_type', 'status', 'priority', 'project', 'created_at')
