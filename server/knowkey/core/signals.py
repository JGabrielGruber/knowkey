import uuid

from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from .models import Node, NodeRelationship


# ====================== VERSIONING ======================
@receiver(pre_save, sender=Node)
def handle_node_versioning(sender, instance, **kwargs):
    """Keep the original Node ID as the stable 'head' (latest version).
    Every meaningful change creates an immutable history 🍄‍🟫."""

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

    # If nothing important changed → just let normal update happen (e.g. metadata only)
    if (
        old.content == instance.content
        and old.summary == instance.summary
        and old.title == instance.title
    ):
        return

    # === CREATE IMMUTABLE HISTORY ROW (🍄‍🟫) ===
    # We copy the OLD state into a new row
    history = Node.objects.create(
        title=old.title,
        summary=old.summary,
        content=old.content,
        embedding=old.embedding,
        node_type=old.node_type,
        author=old.author,
        version_of=old,  # points to the stable head
        version_number=old.version_number,  # keep old number for this history entry
        metadata=old.metadata.copy() if old.metadata else {},
        is_archived=old.is_archived,
        # tags are copied via M2M in post_save (see below)
    )

    # Copy tags to history node
    history.tags.set(old.tags.all())

    # === UPDATE THE HEAD NODE (same ID, now becomes newest) ===
    instance.version_number = old.version_number + 1
    instance.version_of = None  # this node remains the head

    # Note: tags and relationships stay on the head (they belong to the concept)


# ====================== EMBEDDING QUEUE (future-proof) ======================
@receiver(post_save, sender=Node)
def queue_embedding(sender, instance, created, **kwargs):
    """After any save, push to Redis stream so the agent can generate embedding"""
    import json
    import os

    from redis import Redis

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    r = Redis.from_url(redis_url, decode_responses=True)

    payload = {
        "node_id": str(instance.id),
        "action": "generate_embedding",
        "title": instance.title,
        "summary": instance.summary or "",
        "content": instance.content or "",
        "timestamp": str(instance.updated_at),
    }

    r.xadd("knowkey:embedding_jobs", payload, maxlen=10000)
    # This is fire-and-forget — super safe


# ====================== RELATIONSHIP STATS ======================
@receiver(post_save, sender=NodeRelationship)
def update_relationship_stats(sender, instance, **kwargs):
    """Keep metadata stats fresh"""
    # Example: increment discussion_count on target
    if instance.relationship_type == "discusses":
        target = instance.target
        meta = target.metadata or {}
        meta["discussion_count"] = meta.get("discussion_count", 0) + 1
        target.metadata = meta
        target.save(update_fields=["metadata"])


# ====================== SOFT DELETE PROTECTION ======================
@receiver(pre_delete, sender=Node)
def prevent_hard_delete(sender, instance, **kwargs):
    """Never really delete — just archive"""
    instance.is_archived = True
    instance.save()
    raise Exception("Hard delete blocked — node was archived instead")
