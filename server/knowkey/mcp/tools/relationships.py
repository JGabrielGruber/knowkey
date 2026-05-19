"""
Tools: Relationships
====================
Create typed connections between live nodes only.
"""

from asgiref.sync import async_to_sync
from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context
from pydantic import BaseModel, Field

from knowkey.core.models import Node, NodeRelationship, RelationshipType
from knowkey.mcp.server import mcp
from knowkey.mcp.utils import sync_to_async


class CreateRelationshipInput(BaseModel):
    source_node_id: str = Field(..., description="ID of the source (live) node.")
    target_node_id: str = Field(..., description="ID of the target (live) node.")
    relationship_type: str = Field(
        ...,
        description="One of the valid relationship types from knowkey://ontology/relationship_types.",
    )
    weight: float = Field(
        default=1.0, ge=0.0, le=10.0, description="Strength of the relationship."
    )


@mcp.tool
@sync_to_async()
def create_relationship(
    params: CreateRelationshipInput,
    ctx: Context = None,  # type: ignore
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
            f"Creating relationship: {params.relationship_type} "
            f"from {params.source_node_id} → {params.target_node_id}"
        )

    try:
        source = Node.objects.get(id=params.source_node_id)
        target = Node.objects.get(id=params.target_node_id)
    except Node.DoesNotExist:
        raise ToolError("Source or target node not found.")

    if not source.is_latest or not target.is_latest:
        raise ToolError(
            "Both source and target must be live (latest) nodes. "
            "Use search_nodes with include_all_versions=false to find live nodes."
        )

    if params.relationship_type not in [c[0] for c in RelationshipType.choices]:
        valid = [c[0] for c in RelationshipType.choices]
        raise ToolError(f"Invalid relationship_type. Valid options: {valid}")

    author = __import__(
        "knowkey.mcp.core", fromlist=["get_or_create_author"]
    ).get_or_create_author()

    rel = NodeRelationship.objects.create(
        source=source,
        target=target,
        relationship_type=params.relationship_type,
        weight=params.weight,
        created_by=author,
    )

    return {
        "success": True,
        "id": str(rel.id),
        "relationship_type": params.relationship_type,
        "message": "Relationship created successfully between live nodes.",
    }
