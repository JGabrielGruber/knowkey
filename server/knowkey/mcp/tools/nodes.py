"""
Tools: Node Operations
======================
Create, update, revert, and manage nodes.
"""

from typing import Optional

from asgiref.sync import async_to_sync
from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context
from pydantic import BaseModel, Field

from knowkey.mcp.core import create_knowkey_node, serialize_node
from knowkey.mcp.server import mcp
from knowkey.mcp.utils import sync_to_async


# =============================================================================
# CREATE NODE
# =============================================================================
class CreateNodeInput(BaseModel):
    title: str = Field(..., min_length=3, description="Clear, descriptive title.")
    summary: str = Field(
        ...,
        min_length=10,
        description="Excellent 1-3 sentence summary (most important field for discoverability).",
    )
    content: str = Field(default="", description="Full content (markdown supported).")
    node_type_name: str = Field(
        ..., description="Exact NodeType name (see knowkey://ontology/node_types)."
    )
    tag_names: Optional[list[str]] = Field(default=None)
    metadata: Optional[dict] = Field(default=None)
    author_name: str = Field(default="Grok")


@mcp.tool
@sync_to_async()
def create_node(
    params: CreateNodeInput, ctx: Context = None  # type: ignore
) -> dict:
    """
    Create a new **live** node in Knowkey.

    ## Rules
    - Always search first with `search_nodes`.
    - Write a high-quality `summary`.
    - Nodes created via MCP are auto-tagged with `source: mcp`.
    """
    if ctx:
        async_to_sync(ctx.info)(f"Creating node: {params.title}")

    try:
        node = create_knowkey_node(
            title=params.title,
            summary=params.summary,
            content=params.content,
            node_type_name=params.node_type_name,
            tag_names=params.tag_names,
            metadata=params.metadata,
            author_name=params.author_name,
        )
        return {
            "success": True,
            "id": str(node.id),
            "title": node.title,
            "version_number": 1,
            "message": "Live node created successfully.",
        }
    except Exception as e:
        raise ToolError(f"Failed to create node: {str(e)}")


# =============================================================================
# UPDATE NODE
# =============================================================================
class UpdateNodeInput(BaseModel):
    node_id: str = Field(..., description="UUID of the live node to update.")
    title: Optional[str] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    node_type_name: Optional[str] = None
    tag_names: Optional[list[str]] = None


@mcp.tool
@sync_to_async()
def update_node(
    params: UpdateNodeInput, ctx: Context = None  # type: ignore
) -> dict:
    """
    Update a live node.

    This automatically creates a historical snapshot of the old state.
    Use when you want to improve or correct existing knowledge.
    """
    from knowkey.core.models import Node, NodeType

    if ctx:
        async_to_sync(ctx.info)(f"Updating node {params.node_id}")

    try:
        node = Node.objects.get(id=params.node_id, version_of__isnull=True)
    except Node.DoesNotExist:
        raise ToolError("Node not found or is not the live version.")

    changed = False
    if params.title is not None:
        node.title = params.title
        changed = True
    if params.summary is not None:
        node.summary = params.summary
        changed = True
    if params.content is not None:
        node.content = params.content
        changed = True
    if params.node_type_name:
        node.node_type = NodeType.objects.get(name__iexact=params.node_type_name)
        changed = True

    if changed:
        node.save()  # Triggers versioning

    if params.tag_names is not None:
        from knowkey.core.models import Tag

        tags = [Tag.objects.get_or_create(name=t)[0] for t in params.tag_names]
        node.tags.set(tags)

    return {
        "success": True,
        "id": str(node.id),
        "new_version_number": node.version_number,
        "message": "Node updated. Previous version saved as snapshot.",
    }


# =============================================================================
# REVERT NODE
# =============================================================================
class RevertNodeInput(BaseModel):
    node_id: str = Field(
        ..., description="UUID of the **live** node you want to revert."
    )
    snapshot_id: str = Field(
        ...,
        description="UUID of a historical snapshot belonging to this node (from its history).",
    )


@mcp.tool
@sync_to_async()
def revert_node(
    params: RevertNodeInput, ctx: Context = None  # type: ignore
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
        async_to_sync(ctx.info)(
            f"Reverting node {params.node_id} to snapshot {params.snapshot_id}"
        )

    try:
        live_node = Node.objects.get(id=params.node_id, version_of__isnull=True)
        snapshot = Node.objects.get(id=params.snapshot_id, version_of=live_node)
    except Node.DoesNotExist:
        raise ToolError(
            "Live node or snapshot not found. "
            "Make sure snapshot belongs to this node and node is live."
        )

    try:
        live_node.revert_to(snapshot, bypass_versioning=False)
        live_node.save()

        return {
            "success": True,
            "id": str(live_node.id),
            "new_version_number": live_node.version_number,
            "message": f"Successfully reverted to snapshot. New version created.",
            "restored_title": live_node.title,
        }
    except Exception as e:
        raise ToolError(f"Revert failed: {str(e)}")


# =============================================================================
# GET NODE (Tool version for convenience)
# =============================================================================
class GetNodeInput(BaseModel):
    node_id: str = Field(..., description="UUID of the node to retrieve.")


@mcp.tool
@sync_to_async()
def get_node(params: GetNodeInput, ctx: Context = None) -> dict:  # type: ignore
    """
    Retrieve full details of one node (including relationships).

    Useful when you have an ID and need complete context.
    """
    from knowkey.core.models import Node

    if ctx:
        async_to_sync(ctx.info)(f"Fetching node {params.node_id}")

    try:
        node = (
            Node.objects.select_related("node_type", "author")
            .prefetch_related("tags", "outgoing_relationships__target")
            .get(id=params.node_id)
        )
        return serialize_node(node, include_relationships=True)
    except Node.DoesNotExist:
        raise ToolError("Node not found.")
