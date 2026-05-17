from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from knowkey.core.models import Node


# ====================== EMBEDDING QUEUE ======================
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
