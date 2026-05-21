"""
Tools: Relationships
====================
Create typed connections between live nodes + dynamic relationship types.
"""

from asgiref.sync import async_to_sync
from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context
from knowkey.mcp.core import create_relationship as core_create_relationship
from knowkey.mcp.core import create_relationship_type as core_create_relationship_type
from knowkey.mcp.server import mcp
from knowkey.mcp.utils import sync_to_async
from pydantic import Field


@mcp.tool
@sync_to_async()
def create_relationship_type(
    name: str = Field(
        ..., description="Name of the new relationship type (e.g. 'founded_by')"
    ),
    description: str = Field("", description="Clear usage guidance"),
    icon: str = Field("", description="Emoji icon"),
    color: str = Field("", description="Color"),
    ctx: Context | None = None,
) -> dict:
    """Create a new custom RelationshipType."""
    if ctx:
        async_to_sync(ctx.info)(f"Creating RelationshipType: {name}")

    try:
        rt = core_create_relationship_type(
            name=name,
            description=description,
            icon=icon,
            color=color,
        )
        return {
            "success": True,
            "id": str(rt.id),
            "name": rt.name,
            "message": "✅ RelationshipType created.",
        }
    except Exception as e:
        raise ToolError(f"Failed to create RelationshipType: {str(e)}")


@mcp.tool
@sync_to_async()
def create_relationship(
    source_node_id: str = Field(..., description="UUID of source (live) node"),
    target_node_id: str = Field(..., description="UUID of target (live) node"),
    relationship_type_name: str = Field(
        ...,
        description="Exact existing RelationshipType name (e.g. 'discusses', 'answer_to', 'part_of')",
    ),
    weight: float = Field(default=1.0, ge=0.0, le=10.0),
    ctx: Context | None = None,
) -> dict:
    """Create a relationship between two live nodes."""
    if ctx:
        async_to_sync(ctx.info)(
            f"Creating {relationship_type_name} from {source_node_id} → {target_node_id}"
        )

    try:
        relationship = core_create_relationship(
            source_id=source_node_id,
            target_id=target_node_id,
            relationship_type_name=relationship_type_name,
            weight=weight,
        )

        return {
            "success": True,
            "id": str(relationship.id),
            "relationship_type": relationship.relationship_type.name,
            "message": "✅ Relationship created between live nodes.",
        }
    except Exception as e:
        raise ToolError(f"Failed to create relationship: {str(e)}")
