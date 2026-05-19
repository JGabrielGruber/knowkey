"""
Resources: Ontology
===================
Exposes Knowkey's type system and guidance to the LLM.
"""

import json

from fastmcp import FastMCP

from knowkey.core.models import Node, NodeType, RelationshipType, Tag
from knowkey.mcp.server import mcp
from knowkey.mcp.utils import sync_to_async


@mcp.resource("knowkey://ontology/node_types")
@sync_to_async()
def get_node_types() -> str:
    """List all available NodeTypes with descriptions and icons."""
    data = [
        {
            "name": nt.name,
            "description": nt.description,
            "icon": nt.icon,
            "color": nt.color,
        }
        for nt in NodeType.objects.all().order_by("name")
    ]
    return json.dumps(data, indent=2)


@mcp.resource("knowkey://ontology/relationship_types")
@sync_to_async()
def get_relationship_types() -> str:
    """
    List all RelationshipTypes with usage guidance.

    This is critical context for the agent when deciding how to connect nodes.
    """
    guidance = {
        "discusses": "Use when the source node explores, covers, or talks about the target topic.",
        "answers_to": "Use when the source provides an answer or solution to the target (question/problem).",
        "inspired_by": "Use when the source was inspired by or builds upon ideas from the target.",
        "part_of": "Use for hierarchical or compositional relationships (source is part of target).",
        "contradicts": "Use only when there is clear, meaningful opposition. Use sparingly.",
        "has_issue": "Use to flag known problems, limitations, or open questions in the target.",
        "tagged_as": "Use when the source is categorized or labeled by the target concept.",
        "version_of": "Internal use only — do not create manually.",
    }

    data = {
        "types": [
            {
                "value": choice[0],
                "label": choice[1],
                "when_to_use": guidance.get(choice[0], ""),
            }
            for choice in RelationshipType.choices
        ],
        "note": "Always prefer the most specific and accurate relationship type. Search existing nodes first.",
    }
    return json.dumps(data, indent=2)


@mcp.resource("knowkey://ontology/tags")
@sync_to_async()
def get_tags() -> str:
    """List existing tags (useful for consistent tagging)."""
    data = [
        {"name": tag.name, "description": tag.description, "color": tag.color}
        for tag in Tag.objects.all().order_by("name")[:100]
    ]
    return json.dumps(data, indent=2)
