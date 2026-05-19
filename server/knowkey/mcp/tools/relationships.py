"""
Tools: Relationships
====================
Create typed connections between live nodes only.
"""

from asgiref.sync import async_to_sync
from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context
from pydantic import Field

from knowkey.core.models import Node, NodeRelationship, RelationshipType
from knowkey.mcp.server import mcp
from knowkey.mcp.utils import sync_to_async


@mcp.tool
@sync_to_async()
def create_relationship(
    source_node_id: str = Field(..., description="UUID of source (live) node"),
    target_node_id: str = Field(..., description="UUID of target (live) node"),
    relationship_type: str = Field(..., description="Valid type from knowkey://ontology/relationship_types"),
    weight: float = Field(default=1.0, ge=0.0, le=10.0, description="Relationship strength"),
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
        source = Node.objects.get(id=source_node_id)
        target = Node.objects.get(id=target_node_id)
    except Node.DoesNotExist:
        raise ToolError("Source or target node not found.")

    if not source.is_latest or not target.is_latest:
        raise ToolError("Both source and target must be live nodes.")

    valid_types = [c[0] for c in RelationshipType.choices]
    if relationship_type not in valid_types:
        raise ToolError(f"Invalid relationship_type. Valid: {valid_types}")

    author = __import__("knowkey.mcp.core", fromlist=["get_or_create_author"]).get_or_create_author()

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
        "message": "✅ Relationship created between live nodes.",
    }
