
from django.conf import settings
from django.db import models

from apps.workspaces.models import Workspace


class Project(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="projects",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_projects",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name