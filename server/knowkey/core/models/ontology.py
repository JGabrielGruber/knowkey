import uuid

from django.db import models
from django.utils import timezone


class NodeType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Node Type"
        verbose_name_plural = "Node Types"

    def __str__(self):
        return self.name


class RelationshipType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Relationship Type"
        verbose_name_plural = "Relationship Types"

    def __str__(self):
        return self.name


class Tag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
