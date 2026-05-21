"""
knowkey.mcp.core
================
Centralized business logic for Knowkey MCP operations.
All tools and compose flows should call these functions.
"""

import json
from typing import Any, Optional

from django.db import transaction
from knowkey.core.models import (
    Author,
    AuthorType,
    Node,
    NodeRelationship,
    NodeType,
    Tag,
)
from knowkey.mcp.utils import sanitize_name, sanitize_tag_name, standardize_tags


def get_or_create_author(name: str = "Grok", author_type: str = "agent") -> Author:
    """Get or create an Author for MCP operations."""
    author_type = sanitize_tag_name(author_type)
    author, _ = Author.objects.get_or_create(
        name=name,
        defaults={"author_type": author_type},
    )
    return author


def serialize_node(node: Node, include_relationships: bool = False) -> dict[str, Any]:
    """LLM-friendly node serialization."""
    data: dict[str, Any] = {
        "id": str(node.id),
        "title": node.title,
        "summary": node.summary,
        "content": node.content,
        "node_type": {
            "name": node.node_type.name,
            "icon": getattr(node.node_type, "icon", ""),
            "color": getattr(node.node_type, "color", ""),
        },
        "author": {"name": node.author.name},
        "version_number": node.version_number,
        "is_latest": node.is_latest,
        "tags": [t.name for t in node.tags.all()],
        "metadata": node.metadata or {},
        "created_at": node.created_at.isoformat(),
        "updated_at": node.updated_at.isoformat(),
    }

    if include_relationships:
        data["outgoing_relationships"] = [
            {
                "relationship_type": rel.relationship_type,
                "target_id": str(rel.target.id),
                "target_title": rel.target.title,
            }
            for rel in node.outgoing_relationships.select_related("target").all()[:20]
        ]
        data["incoming_relationships"] = [
            {
                "relationship_type": rel.relationship_type,
                "source_id": str(rel.source.id),
                "source_title": rel.source.title,
            }
            for rel in node.incoming_relationships.select_related("source").all()[:20]
        ]
    return data


def serialize_node_list(nodes: list[Node]) -> list[dict]:
    return [
        {
            "id": str(n.id),
            "title": n.title,
            "summary": n.summary,
            "node_type": n.node_type.name,
            "is_latest": n.is_latest,
            "version_number": n.version_number,
            "updated_at": n.updated_at.isoformat(),
        }
        for n in nodes
    ]


# ====================== CORE NODE OPERATIONS ======================


@transaction.atomic
def create_node(
    title: str,
    summary: str,
    node_type_name: str,
    content: str = "",
    tag_names: Optional[list[str]] = None,
    metadata: Optional[dict] = None,
    author_name: str = "Grok",
) -> Node:
    """Create a new live node. Central implementation."""
    tag_names = tag_names or []
    metadata = metadata or {}
    metadata.setdefault("source", "mcp")
    metadata.setdefault("created_via_mcp", True)

    node_type_name = sanitize_name(node_type_name, title_case=True)
    author_name = sanitize_name(author_name, title_case=True)

    node_type = NodeType.objects.get(name__iexact=node_type_name)
    author = get_or_create_author(author_name)

    title = sanitize_name(title)

    node = Node.objects.create(
        title=title,
        summary=summary,
        content=content,
        node_type=node_type,
        author=author,
        metadata=metadata,
    )

    if tag_names:
        tag_names = standardize_tags(tag_names)

        tags = [Tag.objects.get_or_create(name=t)[0] for t in tag_names]
        node.tags.set(tags)

    return node


@transaction.atomic
def update_node(
    node_id: str,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    content: Optional[str] = None,
    node_type_name: Optional[str] = None,
    tag_names: Optional[list[str]] = None,
    metadata: Optional[dict] = None,
) -> Node:
    """Update a live node (creates history snapshot automatically via signal)."""
    node = Node.objects.get(id=node_id, version_of__isnull=True)

    changed = False
    if title is not None:
        title = sanitize_name(title)
        node.title = title
        changed = True
    if summary is not None:
        node.summary = summary
        changed = True
    if content is not None:
        node.content = content
        changed = True
    if metadata is not None:
        node.metadata.update(metadata)
        changed = True

    if node_type_name:
        node_type_name = sanitize_name(node_type_name, title_case=True)
        node.node_type = NodeType.objects.get(name__iexact=node_type_name)
        changed = True

    if changed:
        node.save()  # triggers versioning

    if tag_names is not None:
        tag_names = standardize_tags(tag_names)
        tags = [Tag.objects.get_or_create(name=t)[0] for t in tag_names]
        node.tags.set(tags)

    return node


@transaction.atomic
def revert_node(node_id: str, snapshot_id: str) -> Node:
    """Revert live node to a snapshot."""
    live_node = Node.objects.get(id=node_id, version_of__isnull=True)
    snapshot = Node.objects.get(id=snapshot_id, version_of=live_node)

    live_node.revert_to(snapshot, bypass_versioning=False)
    live_node.save()
    return live_node


@transaction.atomic
def create_relationship(
    source_id: str,
    target_id: str,
    relationship_type: str,
    weight: float = 1.0,
    author_name: str = "Grok",
) -> NodeRelationship:
    """Create relationship between two live nodes only."""
    source = Node.objects.get(id=source_id)
    target = Node.objects.get(id=target_id)

    if not source.is_latest or not target.is_latest:
        raise ValueError("Both source and target must be live nodes.")

    author_name = sanitize_name(author_name, title_case=True)
    author = get_or_create_author(author_name)

    relationship_type = sanitize_tag_name(relationship_type)

    return NodeRelationship.objects.create(
        source=source,
        target=target,
        relationship_type=relationship_type,
        weight=weight,
        created_by=author,
    )


def create_node_type(
    name: str,
    description: str = "",
    icon: str = "",
    color: str = "",
) -> NodeType:
    """Create or get NodeType."""
    name = sanitize_name(name, title_case=True)
    return NodeType.objects.get_or_create(
        name=name,
        defaults={"description": description, "icon": icon, "color": color},
    )[0]


def get_node(node_id: str, include_relationships: bool = True) -> Node:
    return (
        Node.objects.select_related("node_type", "author")
        .prefetch_related(
            "tags", "outgoing_relationships__target", "incoming_relationships__source"
        )
        .get(id=node_id)
    )


# ====================== SEARCH ======================


def search_nodes(
    query: str = "",
    node_type_name: Optional[str] = None,
    tag_names: Optional[list[str]] = None,
    limit: int = 10,
    include_all_versions: bool = False,
) -> list[Node]:
    qs = Node.objects.select_related("node_type").prefetch_related("tags")

    if not include_all_versions:
        qs = qs.filter(version_of__isnull=True)

    if query:
        from django.db.models import Q

        qs = qs.filter(
            Q(title__icontains=query)
            | Q(summary__icontains=query)
            | Q(content__icontains=query)
        )

    if node_type_name:
        node_type_name = sanitize_name(node_type_name, title_case=True)
        qs = qs.filter(node_type__name__iexact=node_type_name)

    if tag_names:
        tag_names = standardize_tags(tag_names)
        for tag in tag_names:
            qs = qs.filter(tags__name__iexact=tag)

    return list(qs.distinct().order_by("-updated_at")[:limit])
