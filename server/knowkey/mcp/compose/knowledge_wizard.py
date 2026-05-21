"""
compose/knowledge_wizard.py
===========================
Sequential Knowledge Wizard with per-step structured models.

Uses core business logic directly (no internal tool calls).
"""

from dataclasses import dataclass, field
from typing import Literal

from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context
from fastmcp.server.sampling import SamplingTool
from knowkey.mcp.core import (
    create_node,
    create_node_type,
    create_relationship,
    search_nodes,
    update_node,
)
from knowkey.mcp.server import mcp
from knowkey.mcp.utils import sync_to_async
from pydantic import BaseModel, Field

# =============================================================================
# Input Models
# =============================================================================


class NodeInput(BaseModel):
    id: str | None = Field(
        default=None, description="If provided → update existing node"
    )
    title: str = Field(..., min_length=3)
    summary: str = Field(..., min_length=10)
    node_type_name: str
    content: str = Field(default="", description="Full content in Markdown")
    tag_names: list[str] = Field(default_factory=list)


class RelationshipInput(BaseModel):
    source_id: str
    target_id: str
    relationship_type: str
    weight: float = 1.0


# =============================================================================
# Per-Step Result Models
# =============================================================================


class CreateMainNodeResult(BaseModel):
    action: Literal["create_node", "cancel"] = "create_node"
    data: NodeInput | None = None
    message: str | None = None


class CreateRelatedNodesResult(BaseModel):
    action: Literal["create_nodes", "skip", "previous", "cancel"] = "create_nodes"
    data: list[NodeInput] = Field(default_factory=list)
    message: str | None = None


class CreateRelationshipsResult(BaseModel):
    action: Literal["create_relationships", "skip", "previous", "cancel"] = (
        "create_relationships"
    )
    data: list[RelationshipInput] = Field(default_factory=list)
    message: str | None = None


class ReviewResult(BaseModel):
    action: Literal["confirm", "previous", "cancel"] = "confirm"
    message: str | None = None


# =============================================================================
# Wizard State
# =============================================================================


@dataclass
class WizardState:
    goal: str
    transcript: str = ""
    current_step_index: int = 0
    main_node: NodeInput | None = None
    related_nodes: list[NodeInput] = field(default_factory=list)
    relationships: list[RelationshipInput] = field(default_factory=list)
    created_ids: list[str] = field(default_factory=list)


# =============================================================================
# Core Action Wrappers (async-safe)
# =============================================================================


@sync_to_async()
def w_search_nodes(query: str, limit: int = 10):
    nodes = search_nodes(query=query, limit=limit)
    return {"results": [n.__dict__ for n in nodes]}  # simplified for wizard


@sync_to_async()
def w_create_node_type(name: str, description: str = "", icon: str = ""):
    nt = create_node_type(name=name, description=description, icon=icon)
    return {"success": True, "id": str(nt.id), "name": nt.name}


@sync_to_async()
def w_create_or_update_node(node: NodeInput):
    if node.id:
        result = update_node(
            node_id=node.id,
            title=node.title,
            summary=node.summary,
            content=node.content,
            node_type_name=node.node_type_name,
            tag_names=node.tag_names,
        )
    else:
        result = create_node(
            title=node.title,
            summary=node.summary,
            node_type_name=node.node_type_name,
            content=node.content,
            tag_names=node.tag_names,
        )
    return {
        "success": True,
        "id": str(result.id),
        "title": result.title,
        "version_number": result.version_number,
    }


@sync_to_async()
def w_create_relationship(rel: RelationshipInput):
    create_relationship(
        source_id=rel.source_id,
        target_id=rel.target_id,
        relationship_type=rel.relationship_type,
        weight=rel.weight,
    )
    return {"success": True}


# =============================================================================
# Step Definitions
# =============================================================================


def get_wizard_steps() -> list[dict]:
    return [
        {
            "id": "create_main_node",
            "description": "Create or update the main node",
            "instructions": "Goal: {goal}\n\nSearch first, then create/update the main node.",
            "tools": [
                SamplingTool.from_function(w_search_nodes, name="search_nodes"),
                SamplingTool.from_function(w_create_node_type, name="create_node_type"),
                SamplingTool.from_function(
                    w_create_or_update_node, name="create_or_update_node"
                ),
            ],
            "result_type": CreateMainNodeResult,
            "can_skip": False,
            "can_previous": False,
        },
        {
            "id": "create_related_nodes",
            "description": "Create related nodes (batch supported)",
            "instructions": "Create supporting nodes related to the main topic.",
            "tools": [
                SamplingTool.from_function(w_search_nodes, name="search_nodes"),
                SamplingTool.from_function(w_create_node_type, name="create_node_type"),
                SamplingTool.from_function(
                    w_create_or_update_node, name="create_or_update_node"
                ),
            ],
            "result_type": CreateRelatedNodesResult,
            "can_skip": True,
            "can_previous": True,
        },
        {
            "id": "create_relationships",
            "description": "Create relationships",
            "instructions": "Define meaningful relationships between nodes.",
            "tools": [
                SamplingTool.from_function(w_search_nodes, name="search_nodes"),
            ],
            "result_type": CreateRelationshipsResult,
            "can_skip": True,
            "can_previous": True,
        },
        {
            "id": "review_and_commit",
            "description": "Review and confirm",
            "instructions": "Review all created content and confirm to persist.",
            "tools": [],
            "result_type": ReviewResult,
            "can_skip": False,
            "can_previous": True,
        },
    ]


# =============================================================================
# Main Wizard Tool
# =============================================================================


@mcp.tool
async def knowledge_wizard(
    goal: str = Field(..., description="High-level goal of this knowledge capture"),
    conversation_transcript: str = Field(default="", description="Optional transcript"),
    ctx: Context | None = None,
) -> dict:
    """Interactive sequential Knowledge Wizard."""

    if ctx:
        await ctx.info(f"[Wizard] Starting | Goal: {goal}")

    state = WizardState(goal=goal, transcript=conversation_transcript)
    steps = get_wizard_steps()

    while state.current_step_index < len(steps):
        step = steps[state.current_step_index]
        step_id = step["id"]

        if not ctx:
            raise ToolError("No context provided")

        await ctx.info(f"[Wizard] → Step: {step_id}")

        result = await ctx.sample(
            messages=[
                {
                    "role": "system",
                    "content": "You are inside the Knowledge Wizard. Follow the current step strictly.",
                },
                {
                    "role": "user",
                    "content": str(step["instructions"].format(goal=state.goal)),
                },
            ],
            tools=step.get("tools", []),
            result_type=step["result_type"],
            temperature=0.2,
        )

        if result.action == "cancel":
            return {"success": False, "message": "Wizard cancelled."}

        if result.action == "previous" and step.get("can_previous"):
            state.current_step_index = max(0, state.current_step_index - 1)
            continue

        if result.action == "skip" and step.get("can_skip"):
            state.current_step_index += 1
            continue

        # Store results
        if step_id == "create_main_node" and result.data:
            state.main_node = result.data
        elif step_id == "create_related_nodes" and result.data:
            state.related_nodes.extend(result.data)
        elif step_id == "create_relationships" and result.data:
            state.relationships.extend(result.data)

        state.current_step_index += 1

    if ctx:
        await ctx.info("[Wizard] Completed all steps.")

    return {
        "success": True,
        "goal": state.goal,
        "main_node": state.main_node.model_dump() if state.main_node else None,
        "related_nodes_count": len(state.related_nodes),
        "relationships_count": len(state.relationships),
    }
