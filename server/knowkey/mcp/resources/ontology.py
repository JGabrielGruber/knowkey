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
    """List all dynamic RelationshipTypes."""
    data = [
        {
            "id": str(rt.id),
            "name": rt.name,
            "description": rt.description,
            "icon": rt.icon,
            "color": rt.color,
        }
        for rt in RelationshipType.objects.all().order_by("name")
    ]
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
