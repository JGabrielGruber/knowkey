"""
Tools: Relationships
====================
Create typed connections between live nodes only.
"""

from asgiref.sync import async_to_sync
from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context
from knowkey.mcp.core import create_relationship as core_create_relationship
from knowkey.mcp.server import mcp
from knowkey.mcp.utils import sync_to_async
from pydantic import Field


@mcp.tool
@sync_to_async()
def create_relationship(
    source_node_id: str = Field(..., description="UUID of source (live) node"),
    target_node_id: str = Field(..., description="UUID of target (live) node"),
    relationship_type: str = Field(
        ..., description="Valid type from knowkey://ontology/relationship_types"
    ),
    weight: float = Field(
        default=1.0, ge=0.0, le=10.0, description="Relationship strength"
    ),
    author_name: str = Field(
        default="Grok", description="Author name for this relationship"
    ),
    ctx: Context | None = None,
) -> dict:
    """
    Create a relationship between two **live** nodes.

    ## Strict Rules
    - Both source and target **must** be the latest version (`is_latest = true`).
    - You cannot create relationships involving historical snapshots.
    - Use `search_nodes` first to find the correct live node IDs.

    This is one of the most important tools for building the knowledge graph.
    """
    if ctx:
        async_to_sync(ctx.info)(
            f"Creating {relationship_type} from {source_node_id} → {target_node_id}"
        )

    try:
        rel = core_create_relationship(
            source_id=source_node_id,
            target_id=target_node_id,
            relationship_type=relationship_type,
            weight=weight,
            author_name=author_name,
        )

        return {
            "success": True,
            "id": str(rel.id),
            "relationship_type": relationship_type,
            "message": "✅ Relationship created between live nodes.",
        }
    except Exception as e:
        raise ToolError(f"Failed to updaet node: {str(e)}")
