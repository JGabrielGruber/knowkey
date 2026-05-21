"""
Tools: Node Operations
======================
Create, update, revert, and manage nodes.
"""

from typing import Optional

from asgiref.sync import async_to_sync
from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context
from knowkey.mcp.core import create_node as core_create_node
from knowkey.mcp.core import create_node_type as core_create_node_type
from knowkey.mcp.core import get_node as core_get_node
from knowkey.mcp.core import revert_node as core_revert_node
from knowkey.mcp.core import serialize_node
from knowkey.mcp.core import update_node as core_update_node
from knowkey.mcp.server import mcp
from knowkey.mcp.utils import sync_to_async
from pydantic import Field


@mcp.tool
@sync_to_async()
def create_node(
    title: str = Field(
        ..., min_length=3, description="Clear, descriptive title (3+ chars)"
    ),
    summary: str = Field(
        ...,
        min_length=10,
        description="High-quality 1-3 sentence summary. Most important field for discoverability.",
    ),
    node_type_name: str = Field(
        ...,
        description="Exact existing NodeType name (e.g. 'Note', 'Person', 'Decision')",
    ),
    content: str = Field(default="", description="Full content (Markdown supported)"),
    tag_names: Optional[list[str]] = Field(
        default=None,
        description="List of tag names (will be created if they don't exist)",
    ),
    metadata: Optional[dict] = Field(default=None, description="Additional metadata"),
    author_name: str = Field(default="Grok", description="Author name for this node"),
    ctx: Context | None = None,
) -> dict:
    """
    Create a new **live** node in Knowkey.

    ## Rules
    - Always search first with `search_nodes`.
    - Write a high-quality `summary`.
    - Nodes created via MCP are auto-tagged with `source: mcp`.
    """
    if ctx:
        async_to_sync(ctx.info)(f"Creating node: {title}")

    try:
        node = core_create_node(
            title=title,
            summary=summary,
            content=content,
            node_type_name=node_type_name,
            tag_names=tag_names,
            metadata=metadata,
            author_name=author_name,
        )
        return {
            "success": True,
            "id": str(node.id),
            "title": node.title,
            "version_number": node.version_number,
            "message": "✅ Live node created successfully.",
        }
    except Exception as e:
        raise ToolError(f"Failed to create node: {str(e)}")


@mcp.tool
@sync_to_async()
def update_node(
    node_id: str = Field(..., description="UUID of the live node to update"),
    title: Optional[str] = Field(None, description="New title"),
    summary: Optional[str] = Field(None, description="New summary"),
    content: Optional[str] = Field(None, description="New content"),
    node_type_name: Optional[str] = Field(None, description="New NodeType name"),
    tag_names: Optional[list[str]] = Field(
        None, description="Replace tags with this list"
    ),
    ctx: Context | None = None,
) -> dict:
    """
    Update a live node.

    This automatically creates a historical snapshot of the old state.
    Use when you want to improve or correct existing knowledge.
    """

    if ctx:
        async_to_sync(ctx.info)(f"Updating node {node_id}")

    try:
        node = core_update_node(
            node_id=node_id,
            title=title,
            summary=summary,
            content=content,
            node_type_name=node_type_name,
            tag_names=tag_names,
        )

        return {
            "success": True,
            "id": str(node.id),
            "new_version_number": node.version_number,
            "message": "✅ Node updated. Previous version saved as snapshot.",
        }
    except Exception as e:
        raise ToolError(f"Failed to update node: {str(e)}")


@mcp.tool
@sync_to_async()
def revert_node(
    node_id: str = Field(..., description="UUID of the live node"),
    snapshot_id: str = Field(
        ..., description="UUID of the historical snapshot to revert to"
    ),
    ctx: Context | None = None,
) -> dict:
    """
    Revert a live node back to a previous snapshot.

    ## When to use
    - You made a mistake and want to undo changes.
    - The current version is worse than a previous one.
    - Self-correction after creating low-quality content.

    ## How it works
    1. Creates a snapshot of the current (bad) state first.
    2. Restores content + tags + relationships from the chosen snapshot.
    3. Increments the version number.

    This is a powerful self-correction tool.
    """

    if ctx:
        async_to_sync(ctx.info)(f"Reverting {node_id} to snapshot {snapshot_id}")

    try:
        live_node = core_revert_node(node_id=node_id, snapshot_id=snapshot_id)

        return {
            "success": True,
            "id": str(live_node.id),
            "new_version_number": live_node.version_number,
            "message": "✅ Successfully reverted.",
            "restored_title": live_node.title,
        }
    except Exception as e:
        raise ToolError(f"Revert failed: {str(e)}")


@mcp.tool
@sync_to_async()
def get_node(
    node_id: str = Field(..., description="UUID of the node to retrieve."),
    ctx: Context | None = None,
) -> dict:
    """
    Retrieve full details of one node (including relationships).

    Useful when you have an ID and need complete context.
    """
    from knowkey.core.models import Node

    if ctx:
        async_to_sync(ctx.info)(f"Fetching node {node_id}")

    try:
        node = core_get_node(node_id=node_id)

        return serialize_node(node, include_relationships=True)
    except Node.DoesNotExist:
        raise ToolError("Node not found.")


@mcp.tool
@sync_to_async()
def create_node_type(
    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Unique name for the NodeType (e.g. 'Decision', 'Concept', 'Person')",
    ),
    description: str = Field(
        "", description="Clear description of what this node type represents"
    ),
    icon: str = Field("", description="Emoji or icon (e.g. '🧠', '📋', '👤')"),
    color: str = Field(
        "", description="Hex color or Tailwind color name (e.g. '#3b82f6', 'blue-500')"
    ),
    ctx: Context | None = None,
) -> dict:
    """
    Create a new NodeType in the ontology.

    Use this when the existing NodeTypes are not sufficient for high-quality knowledge modeling.
    Be conservative — only create when truly needed.
    """
    if ctx:
        async_to_sync(ctx.info)(f"Creating NodeType: {name}")

    try:
        node_type = core_create_node_type(
            name=name,
            description=description,
            icon=icon,
            color=color,
        )

        return {
            "success": True,
            "id": str(node_type.id),
            "name": node_type.name,
            "description": node_type.description,
            "icon": node_type.icon,
            "color": node_type.color,
            "message": "✅ NodeType created successfully.",
        }
    except Exception as e:
        raise ToolError(f"Failed to create NodeType: {str(e)}")
