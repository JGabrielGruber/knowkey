"""
knowkey.mcp.core
================
Shared helpers, serialization, and utilities for the Knowkey MCP server.

This module contains logic that is reused across resources, tools, and prompts.
"""

import json
from typing import Any, Optional

from django.db import transaction
from knowkey.core.models import Author, AuthorType, Node, NodeType, Tag


def get_or_create_author(name: str = "Grok", author_type: str = "agent") -> Author:
    """Get or create an Author for MCP operations (default: Grok as agent)."""
    author, _ = Author.objects.get_or_create(
        name=name,
        defaults={"author_type": author_type},
    )
    return author


def serialize_node(node: Node, include_relationships: bool = False) -> dict[str, Any]:
    """Convert a Node to a clean, LLM-friendly dictionary."""
    data: dict[str, Any] = {
        "id": str(node.id),
        "title": node.title,
        "summary": node.summary,
        "content": node.content,
        "node_type": {
            "name": node.node_type.name,
            "icon": getattr(node.node_type, "icon", ""),
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
    """Lightweight serialization for lists."""
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


@transaction.atomic
def create_knowkey_node(
    title: str,
    summary: str,
    content: str,
    node_type_name: str,
    tag_names: Optional[list[str]] = None,
    metadata: Optional[dict] = None,
    author_name: str = "Grok",
) -> Node:
    """
    Core creation logic with proper metadata tagging for MCP origin.
    Always tags nodes created via MCP.
    """
    tag_names = tag_names or []
    metadata = metadata or {}

    # Tag as coming from MCP
    metadata.setdefault("source", "mcp")
    metadata.setdefault("created_via_mcp", True)

    node_type = NodeType.objects.get(name__iexact=node_type_name)
    author = get_or_create_author(author_name)

    node = Node.objects.create(
        title=title,
        summary=summary,
        content=content,
        node_type=node_type,
        author=author,
        metadata=metadata,
    )

    if tag_names:
        tags = [Tag.objects.get_or_create(name=t)[0] for t in tag_names]
        node.tags.set(tags)

    return node
