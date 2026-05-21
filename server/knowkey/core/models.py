import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from pgvector.django import VectorField


# ====================== ENUMS ======================
class AuthorType(models.TextChoices):
    USER = "user", "User"
    CHATBOT = "chatbot", "Chat Bot"
    AGENT = "agent", "Cli Agent"
    SERVICE = "service", "External Service"


class RelationshipType(models.TextChoices):
    """Common relationship types"""

    DISCUSSES = "discusses", "Discusses"
    ANSWER_TO = "answer_to", "Answers to"
    INSPIRED_BY = "inspired_by", "Inspired by"
    PART_OF = "part_of", "Part of"
    CONTRADICTS = "contradicts", "Contradicts"
    HAS_ISSUE = "has_issue", "Has issue"
    TAGGED_AS = "tagged_as", "Tagged as"
    VERSION_OF = "version_of", "Is version of"


# ==================== MANAGERS =======================
class NodeManager(models.Manager):
    def latest_versions(self):
        """Return only the current (latest) version of each node"""
        return self.filter(version_of__isnull=True)

    def all_versions(self):
        """For history view"""
        return self.all()

    def with_related(self):
        """Optimized for list views"""
        return self.select_related("node_type", "author").prefetch_related("tags")


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


class Node(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    title = models.CharField(max_length=500)
    summary = models.TextField(blank=True)
    content = models.TextField(blank=True)

    embedding = VectorField(dimensions=1536, null=True, blank=True)

    node_type = models.ForeignKey(
        NodeType, on_delete=models.PROTECT, related_name="nodes"
    )
    author = models.ForeignKey(Author, on_delete=models.PROTECT, related_name="nodes")

    version_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="versions",
    )
    version_number = models.PositiveIntegerField(default=1)

    metadata = models.JSONField(default=dict)
    is_archived = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    tags = models.ManyToManyField(Tag, blank=True, related_name="nodes")

    objects = NodeManager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["node_type"]),
            models.Index(fields=["is_archived"]),
            models.Index(fields=["version_of"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.node_type.name})"

    def _copy_outgoing_relationships(self, target_node: "Node"):
        """Internal: copy current outgoing relationships to another node (used for snapshots and revert)."""
        for rel in self.outgoing_relationships.all():
            NodeRelationship.objects.create(
                source=target_node,
                target=rel.target,
                relationship_type=rel.relationship_type,
                weight=rel.weight,
                created_by=rel.created_by,
            )

    @property
    def is_latest(self) -> bool:
        return self.version_of is None

    def revert_to(
        self,
        snapshot: "Node",
        author: Author | None = None,
        bypass_versioning: bool = True,
    ) -> None:
        """Revert the live head node (content + relationships) to a historical snapshot."""
        if self.version_of is not None:
            raise ValueError("Can only revert the live head version.")
        if snapshot.version_of != self:
            raise ValueError("This snapshot does not belong to this node.")

        # 1. First create a history entry of the current (bad) state
        self.create_snapshot(author=author)  # signal will handle this safely

        # 2. Restore content from snapshot to head (BYPASS signal to avoid extra history)
        self._bypass_versioning = bypass_versioning
        self.title = snapshot.title
        self.summary = snapshot.summary
        self.content = snapshot.content
        self.embedding = snapshot.embedding
        self.metadata = snapshot.metadata.copy()
        self.node_type = snapshot.node_type
        self.save()
        delattr(self, "_bypass_versioning")  # cleanup

        self.tags.set(snapshot.tags.all())

        # 3. Restore outgoing relationships (delete current ones first)
        self.outgoing_relationships.all().delete()
        for rel in snapshot.outgoing_relationships.all():
            NodeRelationship.objects.create(
                source=self,
                target=rel.target,
                relationship_type=rel.relationship_type,
                weight=rel.weight,
                created_by=rel.created_by or author,
            )

    def delete(self, *args, **kwargs):
        """Soft delete: archive instead of hard delete.
        Works inside transactions and bulk operations."""
        if not self.is_archived:
            self.is_archived = True
            self.save(update_fields=["is_archived"])
        # Do NOT call super().delete() — this is intentional

    def create_snapshot(self, author: Author | None = None) -> "Node":
        """Manually force a snapshot (useful before big manual changes)."""
        # The signal already does this automatically on content changes.
        # This is just a convenience wrapper if you want to force one.
        self.save()  # triggers the pre_save signal
        return self.versions.latest(
            "version_number"
        )  # return the snapshot just created

    def create_manual_snapshot(self, author: Author | None = None) -> "Node":
        """Force-create a snapshot even if content didn't change.
        Used by admin action for testing/debugging."""
        if self.version_of is not None:
            raise ValueError("Can only snapshot live (head) nodes.")

        history = Node.objects.create(
            title=self.title,
            summary=self.summary,
            content=self.content,
            embedding=self.embedding,
            node_type=self.node_type,
            author=author or self.author,
            version_of=self,
            version_number=self.version_number,
            metadata=self.metadata.copy() if self.metadata else {},
            is_archived=self.is_archived,
        )

        history.tags.set(self.tags.all())

        # Freeze relationships too
        for rel in self.outgoing_relationships.all():
            NodeRelationship.objects.create(
                source=history,
                target=rel.target,
                relationship_type=rel.relationship_type,
                weight=rel.weight,
                created_by=rel.created_by,
            )

        return history

    def get_full_history(self):
        """Return live node + all snapshots, newest first"""
        snapshots = list(self.versions.all().order_by("-version_number"))
        return [self] + snapshots


class NodeRelationship(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    source = models.ForeignKey(
        Node, on_delete=models.CASCADE, related_name="outgoing_relationships"
    )
    target = models.ForeignKey(
        Node, on_delete=models.CASCADE, related_name="incoming_relationships"
    )

    relationship_type = models.ForeignKey(
        RelationshipType,
        on_delete=models.PROTECT,
        related_name="relationships",
    )
    weight = models.FloatField(default=1.0)

    created_by = models.ForeignKey(Author, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ["source", "target", "relationship_type"]
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.source.title} → {self.relationship_type.name} → {self.target.title}"
        )

    def clean(self):
        if self.source.version_of is not None or self.target.version_of is not None:
            raise ValidationError(
                "Relationships can only exist between live (latest) nodes."
            )
