from django.conf import settings
from django.db import models, transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.projects.models import Project


class Issue(models.Model):
    """A single unit of work (task / bug / story / epic) inside a Project.

    An issue has two people attached to it:
      - `created_by` (the REPORTER): who filed it. Server-set, never spoofable.
      - `assignee`: who is doing the work. Optional; may be reassigned.
    Both are used by the permission layer to decide who may edit/delete it.
    """

    class Status(models.TextChoices):
        TODO = "todo", "To Do"
        IN_PROGRESS = "in_progress", "In Progress"
        IN_REVIEW = "in_review", "In Review"
        DONE = "done", "Done"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Type(models.TextChoices):
        TASK = "task", "Task"
        BUG = "bug", "Bug"
        STORY = "story", "Story"
        EPIC = "epic", "Epic"

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="issues",
    )
    issue_type = models.CharField(
        max_length=20,
        choices=Type.choices,
        default=Type.TASK,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.TODO,
    )
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )
    # If the assigned user is removed, keep the issue but leave it unassigned.
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_issues",
    )
    # The reporter. Matches the created_by convention used across the codebase.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reported_issues",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Comment(models.Model):
    """A discussion note on an Issue.

    `author` is server-set to the commenter. Authors own their words (only they
    may edit); managers (workspace owner/admin) may delete for moderation.
    """

    issue = models.ForeignKey(
        Issue,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.author} on {self.issue}"


def attachment_upload_path(instance, filename):
    """Group uploaded files by issue so the media tree stays tidy."""
    return f"attachments/issue_{instance.issue_id}/{filename}"


class Attachment(models.Model):
    """A file uploaded against an Issue (screenshot, log, spec, etc.).

    `uploaded_by` is server-set to the uploader. The uploader owns their file
    (may replace/delete it); managers (workspace owner/admin) may also delete
    for moderation. Storage is backend-agnostic: local /media in dev, S3 in
    prod via django-storages env config (no code change).
    """

    issue = models.ForeignKey(
        Issue,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(upload_to=attachment_upload_path)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.file.name} on {self.issue}"


def delete_attachment_file_on_commit(file):
    """Remove a stored attachment only after its database change commits."""
    if file.name:
        storage = file.storage
        name = file.name
        transaction.on_commit(lambda: storage.delete(name), robust=True)


@receiver(pre_save, sender=Attachment)
def remember_replaced_attachment_file(sender, instance, **kwargs):
    if not instance.pk:
        return

    try:
        previous = sender.objects.only("file").get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    if previous.file.name != instance.file.name:
        instance._replaced_file = previous.file


@receiver(post_save, sender=Attachment)
def delete_replaced_attachment_file(sender, instance, **kwargs):
    previous_file = getattr(instance, "_replaced_file", None)
    if previous_file:
        delete_attachment_file_on_commit(previous_file)
        del instance._replaced_file


@receiver(post_delete, sender=Attachment)
def delete_removed_attachment_file(sender, instance, **kwargs):
    delete_attachment_file_on_commit(instance.file)
