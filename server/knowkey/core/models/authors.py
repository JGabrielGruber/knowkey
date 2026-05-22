import uuid

from django.db import models
from django.utils import timezone


# ====================== ENUMS ======================
class AuthorType(models.TextChoices):
    USER = "user", "User"
    CHATBOT = "chatbot", "Chat Bot"
    AGENT = "agent", "Cli Agent"
    SERVICE = "service", "External Service"


# ====================== MODELS ======================
class Author(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    author_type = models.CharField(max_length=20, choices=AuthorType.choices)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_author_type_display()})"
