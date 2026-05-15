import uuid

from django.db import models
from django.utils import timezone
from pgvector.django import VectorField


# ====================== ENUMS (inside models just like you like) ======================
class AuthorType(models.TextChoices):
    APE = "ape", "🦍 Alpha Ape"
    MONKEY = "monkey", "🐒 Grok Monkey"
    SERVICE = "service", "🗿 External Service"


class RelationshipType(models.TextChoices):
    """Common relationship types — we can add more anytime"""

    DISCUSSES = "discusses", "Discusses"
    ANSWER_TO = "answer_to", "Answers to"
    INSPIRED_BY = "inspired_by", "Inspired by"
    PART_OF = "part_of", "Part of"
    CONTRADICTS = "contradicts", "Contradicts"
    HAS_ISSUE = "has_issue", "Has issue"
    TAGGED_AS = "tagged_as", "Tagged as"
    VERSION_OF = "version_of", "Is version of"  # for 🍄‍🟫


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


class NodeType(models.Model):
    """Dynamic 🍄 types — fully flexible"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=100, unique=True
    )  # e.g. discussion, project, bug, idea
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)  # emoji or icon name
    color = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Tag(models.Model):
    """Reusable tags 🗃️"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Node(models.Model):
    """The sacred 🍄 — every node in the jungle"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    title = models.CharField(max_length=500)
    summary = models.TextField(blank=True)
    content = models.TextField(blank=True)  # full content for Layer 2+

    embedding = VectorField(dimensions=1536, null=True, blank=True)  # pgvector magic

    node_type = models.ForeignKey(
        NodeType, on_delete=models.PROTECT, related_name="nodes"
    )
    author = models.ForeignKey(Author, on_delete=models.PROTECT, related_name="nodes")

    # Versioning 🍄‍🟫
    version_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="versions",
    )
    version_number = models.PositiveIntegerField(default=1)

    metadata = models.JSONField(
        default=dict
    )  # stats, extra fields, discussion_count, etc.
    is_archived = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    # Relationships
    tags = models.ManyToManyField(Tag, blank=True, related_name="nodes")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["node_type"]),
            models.Index(fields=["is_archived"]),
            models.Index(fields=["version_of"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.node_type.name})"


class NodeRelationship(models.Model):
    """The vines 🌿 that connect everything"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    source = models.ForeignKey(
        Node, on_delete=models.CASCADE, related_name="outgoing_relationships"
    )
    target = models.ForeignKey(
        Node, on_delete=models.CASCADE, related_name="incoming_relationships"
    )

    relationship_type = models.CharField(
        max_length=50, choices=RelationshipType.choices
    )
    weight = models.FloatField(default=1.0)

    created_by = models.ForeignKey(Author, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ["source", "target", "relationship_type"]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.source.title} → {self.get_relationship_type_display()} → {self.target.title}"
