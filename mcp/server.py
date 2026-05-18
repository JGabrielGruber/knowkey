#!/usr/bin/env python
"""
Knowkey MCP Server
==================
Model Context Protocol server that exposes Knowkey's knowledge graph
to AI agents (Grok, Claude, Cursor, etc.).

This server allows autonomous exploration and feeding of the knowledge base.

Run with:
    python -m knowkey.mcp.server
or for development:
    fastmcp dev knowkey/mcp/server.py
"""

import json
import os
import sys
from datetime import datetime
from typing import Any, Optional

import django
from django.db import transaction
from mcp.server.fastmcp import FastMCP

# =============================================================================
# Django Setup
# =============================================================================
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "knowkey.settings")

try:
    django.setup()
except Exception as e:
    print(f"Warning: Could not setup Django: {e}", file=sys.stderr)

# Now we can safely import models
from django.db.models import Q

from knowkey.core.models import (
    Author,
    AuthorType,
    Node,
    NodeRelationship,
    NodeType,
    RelationshipType,
    Tag,
)

# =============================================================================
# MCP Server Initialization
# =============================================================================
mcp = FastMCP(
    name="Knowkey",
    instructions="""
    You are connected to Knowkey, a versioned graph-based knowledge base.
    
    Available capabilities:
    - Explore existing nodes and relationships
    - Create new high-quality knowledge nodes from conversations
    - Build meaningful typed relationships between nodes
    - Respect automatic versioning (updates create history)
    
    Always search first before creating. Prefer creating new nodes for new insights.
    Only create relationships between live (latest) nodes.
    """,
)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_or_create_author(name: str = "Grok", author_type: str = "agent") -> Author:
    """Get or create an author for AI agents."""
    author, _ = Author.objects.get_or_create(
        name=name,
        defaults={"author_type": author_type},
    )
    return author


def serialize_node(node: Node, include_relationships: bool = False) -> dict:
    """Serialize a node for MCP responses."""
    data = {
        "id": str(node.id),
        "title": node.title,
        "summary": node.summary,
        "content": node.content,
        "node_type": {
            "id": str(node.node_type.id),
            "name": node.node_type.name,
            "icon": node.node_type.icon,
        },
        "author": {
            "id": str(node.author.id),
            "name": node.author.name,
        },
        "version_number": node.version_number,
        "is_latest": node.is_latest,
        "tags": [{"id": str(t.id), "name": t.name} for t in node.tags.all()],
        "metadata": node.metadata or {},
        "created_at": node.created_at.isoformat(),
        "updated_at": node.updated_at.isoformat(),
    }

    if include_relationships:
        data["outgoing_relationships"] = [
            {
                "id": str(rel.id),
                "relationship_type": rel.relationship_type,
                "target_id": str(rel.target.id),
                "target_title": rel.target.title,
                "weight": rel.weight,
            }
            for rel in node.outgoing_relationships.select_related("target").all()
        ]
        data["incoming_relationships"] = [
            {
                "id": str(rel.id),
                "relationship_type": rel.relationship_type,
                "source_id": str(rel.source.id),
                "source_title": rel.source.title,
                "weight": rel.weight,
            }
            for rel in node.incoming_relationships.select_related("source").all()
        ]

    return data


def serialize_node_list(nodes: list[Node]) -> list[dict]:
    """Lightweight serialization for lists."""
    return [
        {
            "id": str(n.id),
            "title": n.title,
            "summary": n.summary,
            "node_type": {"name": n.node_type.name, "icon": n.node_type.icon},
            "version_number": n.version_number,
            "is_latest": n.is_latest,
            "created_at": n.created_at.isoformat(),
        }
        for n in nodes
    ]


# =============================================================================
# RESOURCES
# =============================================================================


@mcp.resource("knowkey://ontology/node_types")
def get_node_types_resource() -> str:
    """Returns all available NodeTypes with descriptions."""
    node_types = NodeType.objects.all().order_by("name")
    data = [
        {
            "id": str(nt.id),
            "name": nt.name,
            "description": nt.description,
            "icon": nt.icon,
            "color": nt.color,
        }
        for nt in node_types
    ]
    return json.dumps(data, indent=2)


@mcp.resource("knowkey://ontology/relationship_types")
def get_relationship_types_resource() -> str:
    """Returns all RelationshipTypes with usage guidance."""
    data = {
        "relationship_types": [
            {
                "value": rel.value,
                "label": rel.label,
                "description": _get_relationship_description(rel.value),
                "when_to_use": _get_relationship_guidance(rel.value),
            }
            for rel in RelationshipType
        ]
    }
    return json.dumps(data, indent=2)


def _get_relationship_description(rel_type: str) -> str:
    descriptions = {
        "discusses": "The source node discusses or explores the target topic/node.",
        "answers_to": "The source provides an answer or solution to the target (typically a question).",
        "inspired_by": "The source was inspired by or builds upon the ideas in the target.",
        "part_of": "The source is a component, sub-topic, or child of the target.",
        "contradicts": "The source contradicts or presents an opposing view to the target.",
        "has_issue": "The source identifies a known problem, limitation, or open issue in the target.",
        "tagged_as": "The source is categorized or tagged with the target concept.",
        "version_of": "Internal relationship indicating versioning (usually managed automatically).",
    }
    return descriptions.get(rel_type, "Custom relationship type.")


def _get_relationship_guidance(rel_type: str) -> str:
    guidance = {
        "discusses": "Use when one piece of knowledge covers or talks about another topic.",
        "answers_to": "Best for linking answers back to questions or open problems.",
        "inspired_by": "Use for derivative ideas, follow-ups, or evolutionary thoughts.",
        "part_of": "Ideal for hierarchical structures and breaking down complex topics.",
        "contradicts": "Use sparingly and only when there is clear, meaningful opposition.",
        "has_issue": "Useful for tracking known limitations or bugs related to a node.",
    }
    return guidance.get(rel_type, "Use according to your best judgment for the domain.")


@mcp.resource("knowkey://node/{node_id}")
def get_node_resource(node_id: str) -> str:
    """Returns full details of a specific node including relationships."""
    try:
        node = (
            Node.objects.select_related("node_type", "author")
            .prefetch_related("tags", "outgoing_relationships__target", "incoming_relationships__source")
            .get(id=node_id)
        )
        return json.dumps(serialize_node(node, include_relationships=True), indent=2)
    except Node.DoesNotExist:
        return json.dumps({"error": f"Node with id {node_id} not found"})


# =============================================================================
# TOOLS
# =============================================================================


@mcp.tool()
def search_nodes(
    query: str,
    node_type_name: Optional[str] = None,
    tag_names: Optional[list[str]] = None,
    limit: int = 10,
    include_all_versions: bool = False,
) -> list[dict]:
    """
    Search for nodes using keyword matching and filters.

    Use this tool first before creating new knowledge.
    Returns live nodes by default.
    """
    qs = Node.objects.select_related("node_type", "author").prefetch_related("tags")

    if not include_all_versions:
        qs = qs.filter(version_of__isnull=True)  # Only live nodes

    # Keyword search on title, summary, content
    if query:
        qs = qs.filter(
            Q(title__icontains=query)
            | Q(summary__icontains=query)
            | Q(content__icontains=query)
        )

    if node_type_name:
        qs = qs.filter(node_type__name__iexact=node_type_name)

    if tag_names:
        for tag_name in tag_names:
            qs = qs.filter(tags__name__iexact=tag_name)

    qs = qs.distinct().order_by("-updated_at")[:limit]

    return serialize_node_list(list(qs))


@mcp.tool()
def get_node(node_id: str) -> dict:
    """
    Retrieve full details of a node including its relationships.

    Use this when you need the complete content of a node.
    """
    try:
        node = (
            Node.objects.select_related("node_type", "author")
            .prefetch_related("tags", "outgoing_relationships__target", "incoming_relationships__source")
            .get(id=node_id)
        )
        return serialize_node(node, include_relationships=True)
    except Node.DoesNotExist:
        return {"error": f"Node {node_id} not found"}


@mcp.tool()
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
    Create a new live knowledge node in Knowkey.

    This is the primary tool for feeding new knowledge from conversations.
    The node will be created as version 1 (live).
    Embedding generation is triggered automatically.
    """
    tag_names = tag_names or []
    metadata = metadata or {}

    try:
        with transaction.atomic():
            # Resolve NodeType
            try:
                node_type = NodeType.objects.get(name__iexact=node_type_name)
            except NodeType.DoesNotExist:
                return {"error": f"NodeType '{node_type_name}' does not exist. Please check available types."}

            # Get or create author
            author = get_or_create_author(name=author_name)

            # Create the node
            node = Node.objects.create(
                title=title,
                summary=summary,
                content=content,
                node_type=node_type,
                author=author,
                metadata=metadata,
            )

            # Attach tags
            if tag_names:
                tags = []
                for tag_name in tag_names:
                    tag, _ = Tag.objects.get_or_create(name=tag_name)
                    tags.append(tag)
                node.tags.set(tags)

            return {
                "id": str(node.id),
                "title": node.title,
                "version_number": node.version_number,
                "is_latest": True,
                "node_type": node_type.name,
                "message": "Node created successfully. Embedding will be generated asynchronously.",
            }

    except Exception as e:
        return {"error": f"Failed to create node: {str(e)}"}


@mcp.tool()
def create_relationship(
    source_node_id: str,
    target_node_id: str,
    relationship_type: str,
    weight: float = 1.0,
    created_by_author_name: str = "Grok",
) -> dict:
    """
    Create a typed relationship between two LIVE nodes.

    IMPORTANT: Both source and target must be the latest version (live nodes).
    """
    try:
        source = Node.objects.get(id=source_node_id)
        target = Node.objects.get(id=target_node_id)

        if not source.is_latest or not target.is_latest:
            return {
                "error": "Relationships can only be created between live (latest) nodes. "
                "Please use the live version IDs."
            }

        # Validate relationship type
        valid_types = [choice[0] for choice in RelationshipType.choices]
        if relationship_type not in valid_types:
            return {"error": f"Invalid relationship_type. Must be one of: {valid_types}"}

        author = get_or_create_author(name=created_by_author_name)

        rel = NodeRelationship.objects.create(
            source=source,
            target=target,
            relationship_type=relationship_type,
            weight=weight,
            created_by=author,
        )

        return {
            "id": str(rel.id),
            "relationship_type": rel.relationship_type,
            "source_title": source.title,
            "target_title": target.title,
            "message": "Relationship created successfully.",
        }

    except Node.DoesNotExist:
        return {"error": "One or both nodes not found."}
    except Exception as e:
        return {"error": f"Failed to create relationship: {str(e)}"}


# =============================================================================
# PROMPTS
# =============================================================================


@mcp.prompt()
def extract_and_persist_knowledge(
    conversation_transcript: str,
    focus_area: str = "General knowledge extraction",
    max_nodes_to_create: int = 3,
) -> list:
    """
    Analyzes a conversation and persists valuable knowledge into Knowkey.

    This is the main workflow prompt for autonomous knowledge feeding.
    """
    from mcp.server.fastmcp.prompts import base

    system_prompt = f"""You are Knowkey's autonomous Knowledge Curator.

Follow these steps strictly:

1. Read the resources:
   - knowkey://ontology/node_types
   - knowkey://ontology/relationship_types

2. Search for relevant existing knowledge using search_nodes.

3. Extract the most valuable insights, decisions, questions/answers, and facts.

4. Create at most {max_nodes_to_create} high-quality nodes using create_node.
   - Choose appropriate node_type_name
   - Write excellent summaries
   - Include rich content and provenance in metadata

5. Link new nodes to relevant existing nodes using create_relationship with precise types.

6. Follow the curation guidelines:
   - Prefer new nodes over updating old ones for new insights
   - Only link live nodes
   - Be thoughtful and selective

Focus area: {focus_area}
"""

    user_message = f"""Please extract and persist valuable knowledge from this conversation:

{conversation_transcript}
"""

    return [
        base.Message(role="system", content=system_prompt),
        base.Message(role="user", content=user_message),
    ]


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("Starting Knowkey MCP Server...")
    mcp.run()
