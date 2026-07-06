from django.contrib import admin

from .models import Project

# Register your models here.

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'workspace',
                    'created_by', 'created_at', 'updated_at')
    search_fields = ('name', 'description')
    list_filter = ('workspace', 'created_at', 'updated_at')
