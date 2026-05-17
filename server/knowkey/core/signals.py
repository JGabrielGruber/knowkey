from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Node, NodeRelationship


# ====================== VERSIONING + RELATIONSHIP SNAPSHOTS ======================
@receiver(pre_save, sender=Node)
def handle_node_versioning(sender, instance, **kwargs):
    """Keep the original Node ID as the stable 'head' (latest version).
    Every meaningful content change creates an immutable history row
    AND freezes the current outgoing relationships."""

    # NEW: Allow revert_to() to restore without creating duplicate history
    if getattr(instance, "_bypass_versioning", False):
        return

    if not instance.pk:
        # Brand new node → this becomes the head
        instance.version_number = 1
        instance.version_of = None
        return

    # We are updating an existing node (the current head)
    try:
        old = Node.objects.get(pk=instance.pk)
    except Node.DoesNotExist:
        return

    # If nothing important changed → skip history (e.g. metadata, tags only)
    if (
        old.content == instance.content
        and old.summary == instance.summary
        and old.title == instance.title
    ):
        return

    # === 1. CREATE IMMUTABLE HISTORY ROW ===
    history = Node.objects.create(
        title=old.title,
        summary=old.summary,
        content=old.content,
        embedding=old.embedding,
        node_type=old.node_type,
        author=old.author,
        version_of=old,  # points to stable head
        version_number=old.version_number,  # history keeps the version it represents
        metadata=old.metadata.copy() if old.metadata else {},
        is_archived=old.is_archived,
    )

    # Copy tags
    history.tags.set(old.tags.all())

    # === 2. FREEZE OUTGOING RELATIONSHIPS ===
    for rel in old.outgoing_relationships.all():
        NodeRelationship.objects.create(
            source=history,  # relationship belongs to this historical snapshot
            target=rel.target,  # still points to live target
            relationship_type=rel.relationship_type,
            weight=rel.weight,
            created_by=rel.created_by,
        )

    # === 3. UPDATE THE HEAD NODE (same ID, becomes newest) ===
    instance.version_number = old.version_number + 1
    instance.version_of = None  # remains the head

    # Note: tags + relationships stay on the head (current state)


# ====================== RELATIONSHIP STATS ======================
@receiver(post_save, sender=NodeRelationship)
def update_relationship_stats(sender, instance, **kwargs):
    """Keep metadata stats fresh"""
    if instance.relationship_type == "discusses":
        target = instance.target
        meta = target.metadata or {}
        meta["discussion_count"] = meta.get("discussion_count", 0) + 1
        target.metadata = meta
        target.save(update_fields=["metadata"])
