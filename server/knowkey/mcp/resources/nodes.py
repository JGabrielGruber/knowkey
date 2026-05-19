"""
Resources: Nodes
===============
Dynamic resources for reading specific nodes and their history.
"""

import json

from fastmcp import FastMCP
from knowkey.core.models import Node
from knowkey.mcp.core import serialize_node
from knowkey.mcp.server import mcp
from knowkey.mcp.utils import sync_to_async


@mcp.resource("knowkey://node/{node_id}")
@sync_to_async()
def read_node(node_id: str) -> str:
    """
    Get full details of a specific node, including relationships.

    Use this when you need deep context about one piece of knowledge.
    """
    try:
        node = (
            Node.objects.select_related("node_type", "author")
            .prefetch_related(
                "tags",
                "outgoing_relationships__target",
                "incoming_relationships__source",
            )
            .get(id=node_id)
        )
        return json.dumps(serialize_node(node, include_relationships=True), indent=2)
    except Node.DoesNotExist:
        return json.dumps({"error": "Node not found", "node_id": node_id})


@mcp.resource("knowkey://node/{node_id}/history")
@sync_to_async()
def read_node_history(node_id: str) -> str:
    """
    Return the full version history of a node (newest first).

    Useful before deciding to revert.
    """
    try:
        node = Node.objects.get(id=node_id)
        history = node.get_full_history()
        return json.dumps(
            {
                "live_node_id": str(node.id),
                "current_version": node.version_number,
                "history": [
                    {
                        "id": str(h.id),
                        "version_number": h.version_number,
                        "title": h.title,
                        "is_latest": h.is_latest,
                        "created_at": h.created_at.isoformat(),
                    }
                    for h in history
                ],
            },
            indent=2,
        )
    except Node.DoesNotExist:
        return json.dumps({"error": "Node not found"})
