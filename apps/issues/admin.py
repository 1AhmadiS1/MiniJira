from django.contrib import admin

from .models import Issue, Comment, Attachment


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'issue_type', 'status', 'priority',
                    'assignee', 'created_by', 'created_at', 'updated_at')
    search_fields = ('title', 'description')
    list_filter = ('issue_type', 'status', 'priority', 'project', 'created_at')


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('issue', 'author', 'created_at', 'updated_at')
    search_fields = ('body',)
    list_filter = ('created_at',)


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ('file', 'issue', 'uploaded_by', 'created_at')
    list_filter = ('created_at',)
