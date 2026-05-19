"""
Tools: Node Operations
======================
Create, update, revert, and manage nodes.
"""

from typing import Optional

from asgiref.sync import async_to_sync
from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context
from pydantic import Field

from knowkey.mcp.core import create_knowkey_node, serialize_node
from knowkey.mcp.server import mcp
from knowkey.mcp.utils import sync_to_async


@mcp.tool
@sync_to_async()
def create_node(
    title: str = Field(..., min_length=3, description="Clear, descriptive title (3+ chars)"),
    summary: str = Field(..., min_length=10, description="High-quality 1-3 sentence summary. Most important field for discoverability."),
    node_type_name: str = Field(..., description="Exact existing NodeType name (e.g. 'Note', 'Person', 'Decision')"),
    content: str = Field(default="", description="Full content (Markdown supported)"),
    tag_names: Optional[list[str]] = Field(default=None, description="List of tag names (will be created if they don't exist)"),
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
        node = create_knowkey_node(
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
    tag_names: Optional[list[str]] = Field(None, description="Replace tags with this list"),
    ctx: Context | None = None,
) -> dict:
    """
    Update a live node.

    This automatically creates a historical snapshot of the old state.
    Use when you want to improve or correct existing knowledge.
    """
    from knowkey.core.models import Node, NodeType

    if ctx:
        async_to_sync(ctx.info)(f"Updating node {node_id}")

    try:
        node = Node.objects.get(id=node_id, version_of__isnull=True)
    except Node.DoesNotExist:
        raise ToolError("Node not found or is not the live version.")

    changed = False
    if title is not None:
        node.title = title
        changed = True
    if summary is not None:
        node.summary = summary
        changed = True
    if content is not None:
        node.content = content
        changed = True
    if node_type_name:
        try:
            node.node_type = NodeType.objects.get(name__iexact=node_type_name)
            changed = True
        except NodeType.DoesNotExist:
            raise ToolError(f"NodeType '{node_type_name}' not found.")

    if changed:
        node.save()  # Triggers versioning signal

    if tag_names is not None:
        from knowkey.core.models import Tag
        tags = [Tag.objects.get_or_create(name=t)[0] for t in tag_names]
        node.tags.set(tags)

    return {
        "success": True,
        "id": str(node.id),
        "new_version_number": node.version_number,
        "message": "✅ Node updated. Previous version saved as snapshot.",
    }


@mcp.tool
@sync_to_async()
def revert_node(
    node_id: str = Field(..., description="UUID of the live node"),
    snapshot_id: str = Field(..., description="UUID of the historical snapshot to revert to"),
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
    from knowkey.core.models import Node

    if ctx:
        async_to_sync(ctx.info)(f"Reverting {node_id} to snapshot {snapshot_id}")

    try:
        live_node = Node.objects.get(id=node_id, version_of__isnull=True)
        snapshot = Node.objects.get(id=snapshot_id, version_of=live_node)
    except Node.DoesNotExist:
        raise ToolError("Live node or valid snapshot not found.")

    try:
        live_node.revert_to(snapshot, bypass_versioning=False)
        live_node.save()

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
    ctx: Context | None = None
) -> dict:
    """
    Retrieve full details of one node (including relationships).

    Useful when you have an ID and need complete context.
    """
    from knowkey.core.models import Node

    if ctx:
        async_to_sync(ctx.info)(f"Fetching node {node_id}")

    try:
        node = (
            Node.objects.select_related("node_type", "author")
            .prefetch_related("tags", "outgoing_relationships__target")
            .get(id=node_id)
        )
        return serialize_node(node, include_relationships=True)
    except Node.DoesNotExist:
        raise ToolError("Node not found.")
