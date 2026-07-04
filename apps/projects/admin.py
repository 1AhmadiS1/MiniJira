from django.contrib import admin

# Register your models here.
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'workspace', 'created_by', 'created_at', 'updated_at')
    search_fields = ('name', 'description')
    list_filter = ('workspace', 'created_at', 'updated_at')
