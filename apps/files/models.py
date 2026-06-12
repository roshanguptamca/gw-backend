import uuid

from django.conf import settings
from django.db import models


class UserFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="career_files"
    )
    anonymous_identity = models.ForeignKey(
        "resumes.AnonymousResumeIdentity",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="career_files",
    )
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120)
    file_size = models.PositiveIntegerField()
    file_data = models.BinaryField(editable=False)
    purpose = models.CharField(max_length=40, default="export")
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
