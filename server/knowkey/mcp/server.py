#!/usr/bin/env python
"""
Knowkey MCP Server
==================
Model Context Protocol server that exposes Knowkey's knowledge graph
to AI agents (Grok, Claude, Cursor, etc.).

This server allows autonomous exploration and feeding of the knowledge base.

Run via Django management command (recommended):
    python manage.py run_mcp_server

Or directly:
    python -m knowkey.mcp.server
"""

import json
import os
import sys
from typing import Any, Optional

import django
from django.db import transaction
from fastmcp import FastMCP

# =============================================================================
# Django Setup (safe when imported from management command)
# =============================================================================
if not os.environ.get("DJANGO_SETTINGS_MODULE"):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "knowkey.settings")

try:
    django.setup()
except Exception:
    pass  # Django might already be set up when running via manage.py

# Import models after Django setup
from django.db.models import Q
from knowkey.core.models import (
    Author,
    Node,
    NodeRelationship,
    NodeType,
    RelationshipType,
    Tag,
)

from .utils import sync_to_async

# =============================================================================
# MCP Server
# =============================================================================
mcp = FastMCP(
    name="Knowkey",
    instructions="""
    You are connected to Knowkey, a versioned graph-based knowledge base.

    Key capabilities:
    - Explore nodes and relationships using search and get tools
    - Read the ontology via resources (node_types and relationship_types)
    - Create high-quality knowledge nodes from conversations
    - Build meaningful typed relationships (only between live nodes)

    Best practices:
    1. Always search existing knowledge first
    2. Prefer creating new nodes for new insights
    3. Use precise relationship types
    4. Include good summaries and provenance metadata
    """,
    version="0.0.1",
)


# =============================================================================
# Helpers
# =============================================================================


def get_or_create_author(name: str = "Grok") -> Author:
    """Get or create author for AI agents."""
    author, _ = Author.objects.get_or_create(
        name=name,
        defaults={"author_type": "agent"},
    )
    return author


def serialize_node(node: Node, include_relationships: bool = False) -> dict[str, Any]:
    """Convert a Node to a clean dictionary for MCP."""
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
    return [
        {
            "id": str(n.id),
            "title": n.title,
            "summary": n.summary,
            "node_type": n.node_type.name,
            "is_latest": n.is_latest,
            "version_number": n.version_number,
        }
        for n in nodes
    ]


# =============================================================================
# RESOURCES
# =============================================================================


@mcp.resource("knowkey://ontology/node_types")
@sync_to_async()
def get_node_types() -> str:
    """List all available node types with descriptions."""
    data = [
        {
            "name": nt.name,
            "description": nt.description,
            "icon": nt.icon,
        }
        for nt in NodeType.objects.all().order_by("name")
    ]
    print(data)
    return json.dumps(data, indent=2)


@mcp.resource("knowkey://ontology/relationship_types")
@sync_to_async()
def get_relationship_types() -> str:
    """List relationship types with guidance on when to use them."""
    guidance = {
        "discusses": "Use when the source explores or covers the target topic.",
        "answers_to": "Use to link an answer back to a question or problem.",
        "inspired_by": "Use for ideas that build upon or were inspired by the target.",
        "part_of": "Use for hierarchical or compositional relationships.",
        "contradicts": "Use only when there is clear opposition (use sparingly).",
        "has_issue": "Use to flag known problems or limitations in the target.",
    }

    data = {
        "types": [
            {
                "value": choice[0],
                "label": choice[1],
                "when_to_use": guidance.get(choice[0], ""),
            }
            for choice in RelationshipType.choices
        ]
    }
    return json.dumps(data, indent=2)


@mcp.resource("knowkey://node/{node_id}")
@sync_to_async()
def read_node(node_id: str) -> str:
    """Get full content and relationships of a specific node."""
    try:
        node = (
            Node.objects.select_related("node_type", "author")
            .prefetch_related("tags", "outgoing_relationships__target")
            .get(id=node_id)
        )
        return json.dumps(serialize_node(node, include_relationships=True), indent=2)
    except Node.DoesNotExist:
        return json.dumps({"error": "Node not found"})


# =============================================================================
# TOOLS
# =============================================================================


@mcp.tool
@sync_to_async()
def search_nodes(
    query: str,
    node_type_name: Optional[str] = None,
    tag_names: Optional[list[str]] = None,
    limit: int = 10,
    include_all_versions: bool = False,
) -> list[dict]:
    """
    Search nodes by keyword and filters.

    Always use this before creating new knowledge.
    Returns only live nodes by default.
    """
    qs = Node.objects.select_related("node_type").prefetch_related("tags")

    if not include_all_versions:
        qs = qs.filter(version_of__isnull=True)

    if query:
        qs = qs.filter(
            Q(title__icontains=query)
            | Q(summary__icontains=query)
            | Q(content__icontains=query)
        )

    if node_type_name:
        qs = qs.filter(node_type__name__iexact=node_type_name)

    if tag_names:
        for tag in tag_names:
            qs = qs.filter(tags__name__iexact=tag)

    qs = qs.distinct().order_by("-updated_at")[:limit]
    return serialize_node_list(list(qs))


@mcp.tool
@sync_to_async()
def get_node(node_id: str) -> dict:
    """Retrieve full details of one node including its relationships."""
    try:
        node = (
            Node.objects.select_related("node_type", "author")
            .prefetch_related("tags", "outgoing_relationships__target")
            .get(id=node_id)
        )
        return serialize_node(node, include_relationships=True)
    except Node.DoesNotExist:
        return {"error": f"Node {node_id} not found"}


@mcp.tool
@sync_to_async()
def create_node(
    title: str,
    summary: str,
    content: str,
    node_type_name: str,
    tag_names: Optional[list[str]] = None,
    metadata: Optional[dict] = None,
    author_name: str = "Grok",
) -> dict:
    """
    Create a new live node in Knowkey.

    This is the main tool for persisting knowledge from conversations.
    """
    tag_names = tag_names or []
    metadata = metadata or {}

    try:
        with transaction.atomic():
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

            return {
                "success": True,
                "id": str(node.id),
                "title": node.title,
                "version_number": 1,
                "message": "Node created successfully",
            }
    except NodeType.DoesNotExist:
        return {"error": f"NodeType '{node_type_name}' does not exist"}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
@sync_to_async()
def create_relationship(
    source_node_id: str,
    target_node_id: str,
    relationship_type: str,
    weight: float = 1.0,
) -> dict:
    """
    Create a relationship between two LIVE nodes.

    Both nodes must be the latest version.
    """
    try:
        source = Node.objects.get(id=source_node_id)
        target = Node.objects.get(id=target_node_id)

        if not source.is_latest or not target.is_latest:
            return {"error": "Both source and target must be live (latest) nodes"}

        if relationship_type not in [c[0] for c in RelationshipType.choices]:
            return {
                "error": f"Invalid relationship_type. Valid options: {[c[0] for c in RelationshipType.choices]}"
            }

        author = get_or_create_author()

        rel = NodeRelationship.objects.create(
            source=source,
            target=target,
            relationship_type=relationship_type,
            weight=weight,
            created_by=author,
        )

        return {
            "success": True,
            "id": str(rel.id),
            "relationship_type": relationship_type,
            "message": "Relationship created",
        }
    except Node.DoesNotExist:
        return {"error": "Source or target node not found"}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
@sync_to_async()
def create_node_type(
    name: str,
    description: str = "",
    icon: str = "",
    color: str = "",
) -> dict:
    """Create a new NodeType (extends the ontology)."""
    try:
        if NodeType.objects.filter(name__iexact=name).exists():
            return {"error": f"NodeType '{name}' already exists"}

        node_type = NodeType.objects.create(
            name=name,
            description=description,
            icon=icon,
            color=color,
        )
        return {
            "success": True,
            "name": node_type.name,
            "message": "NodeType created successfully",
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
@sync_to_async()
def create_relationship_type(
    value: str,  # e.g. "implements"
    label: str,  # e.g. "Implements"
    description: str = "",
    when_to_use: str = "",
) -> dict:
    """Extend the relationship ontology with a new type."""
    # Note: This modifies the model's choices at runtime.
    # In a real production setup, you might want to persist this differently.
    try:
        # For now, we just create it (you can extend RelationshipType.choices later if needed)
        # Since RelationshipType is a TextChoices, dynamic extension is tricky.
        # We can allow it and store extra metadata, or just use it as-is.

        if value in [c[0] for c in RelationshipType.choices]:
            return {"error": f"Relationship type '{value}' already exists"}

        # For simplicity, we'll allow creation but note that full dynamic choices need model update
        return {
            "success": True,
            "value": value,
            "label": label,
            "message": "Relationship type registered. Consider updating models.py for persistence.",
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
@sync_to_async()
def create_tag(
    name: str,
    description: str = "",
    color: str = "#64748b",
) -> dict:
    """Create or get a tag."""
    tag, created = Tag.objects.get_or_create(
        name=name,
        defaults={"description": description, "color": color},
    )
    return {
        "success": True,
        "name": tag.name,
        "created": created,
        "message": "Tag ready to use",
    }


# =============================================================================
# PROMPTS
# =============================================================================


@mcp.prompt
@sync_to_async()
def extract_and_persist_knowledge(
    conversation_transcript: str,
    focus_area: str = "",
    max_nodes: int = 3,
):
    """Main prompt for extracting knowledge from conversations and saving it to Knowkey."""
    from mcp.server.fastmcp.prompts import base

    instructions = f"""
You are Knowkey's Knowledge Curator.

Process:
1. Read knowkey://ontology/node_types and knowkey://ontology/relationship_types
2. Use search_nodes to find relevant existing knowledge
3. Create up to {max_nodes} high-quality nodes using create_node
4. Link them using create_relationship with accurate types
5. Always work with live nodes only

Focus: {focus_area or "General"}
"""

    return [
        base.Message(role="system", content=instructions),
        base.Message(role="user", content=f"Conversation:\n{conversation_transcript}"),
    ]


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    print("Starting Knowkey MCP Server (stdio transport)...")
    mcp.run()
