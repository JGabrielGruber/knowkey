"""
compose/knowledge_wizard.py
===========================
Sequential Knowledge Wizard with per-step structured models.
"""

from dataclasses import dataclass, field
from typing import Literal

from fastmcp.server.context import Context
from fastmcp.server.sampling import SamplingTool
from knowkey.mcp.server import mcp
from knowkey.mcp.utils import sync_to_async
from pydantic import BaseModel, Field

# =============================================================================
# Shared Input Models
# =============================================================================


class NodeInput(BaseModel):
    """Can be used for both create and update."""

    id: str | None = Field(
        default=None,
        description="If provided, update existing node. Otherwise create new.",
    )
    title: str
    summary: str
    node_type_name: str
    content: str = ""
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
    data: list[NodeInput] = Field(default_factory=list)  # batch supported
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
# Smart Wrappers
# =============================================================================


async def create_or_update_node(node: NodeInput) -> dict:
    """
    Smart wrapper: creates or updates based on whether id is present.
    """
    if node.id:
        from knowkey.mcp.tools.nodes import update_node

        return update_node(
            node_id=node.id,
            title=node.title,
            summary=node.summary,
            content=node.content,
            node_type_name=node.node_type_name,
            tag_names=node.tag_names,
        )
    else:
        from knowkey.mcp.tools.nodes import create_node

        return create_node(
            title=node.title,
            summary=node.summary,
            node_type_name=node.node_type_name,
            content=node.content,
            tag_names=node.tag_names,
        )


async def w_search_nodes(query: str, limit: int = 10) -> dict:
    from knowkey.mcp.tools.search import search_nodes

    return {"results": search_nodes(query=query, limit=limit)}


async def w_create_node_type(name: str, description: str = "", icon: str = "") -> dict:
    from knowkey.mcp.tools.nodes import create_node_type

    return create_node_type(name=name, description=description, icon=icon)


# =============================================================================
# Step Definitions with Specific Models
# =============================================================================


def get_wizard_steps() -> list[dict]:
    return [
        # === STEP 1: Main Node ===
        {
            "id": "create_main_node",
            "description": "Create or update the main node",
            "instructions": (
                "Goal: {goal}\n\n"
                "Search first if needed. Then create or update the main node.\n"
                "Use create_or_update_node (it handles both cases)."
            ),
            "tools": [
                SamplingTool.from_function(w_search_nodes, name="search_nodes"),
                SamplingTool.from_function(w_create_node_type, name="create_node_type"),
                SamplingTool.from_function(
                    create_or_update_node, name="create_or_update_node"
                ),
            ],
            "result_type": CreateMainNodeResult,
            "available_actions": ["create_node", "cancel"],
            "can_skip": False,
            "can_previous": False,
        },
        # === STEP 2: Related Nodes (Batch supported) ===
        {
            "id": "create_related_nodes",
            "description": "Create or update related nodes (batch supported)",
            "instructions": (
                "Create or update multiple related nodes.\n"
                "You can return a list of NodeInput objects."
            ),
            "tools": [
                SamplingTool.from_function(w_search_nodes, name="search_nodes"),
                SamplingTool.from_function(w_create_node_type, name="create_node_type"),
                SamplingTool.from_function(
                    create_or_update_node, name="create_or_update_node"
                ),
            ],
            "result_type": CreateRelatedNodesResult,
            "available_actions": ["create_nodes", "skip", "previous", "cancel"],
            "can_skip": True,
            "can_previous": True,
        },
        # === STEP 3: Relationships ===
        {
            "id": "create_relationships",
            "description": "Create relationships between nodes",
            "instructions": "Create relationships using the nodes from previous steps.",
            "tools": [
                SamplingTool.from_function(w_search_nodes, name="search_nodes"),
            ],
            "result_type": CreateRelationshipsResult,
            "available_actions": ["create_relationships", "skip", "previous", "cancel"],
            "can_skip": True,
            "can_previous": True,
        },
        # === STEP 4: Review ===
        {
            "id": "review_and_commit",
            "description": "Final review and confirmation",
            "instructions": "Review all changes and confirm to persist everything.",
            "tools": [],
            "result_type": ReviewResult,
            "available_actions": ["confirm", "previous", "cancel"],
            "can_skip": False,
            "can_previous": True,
        },
    ]


# =============================================================================
# Main Wizard Tool
# =============================================================================


@mcp.tool
async def knowledge_wizard(
    goal: str = Field(..., description="What are we trying to capture or improve?"),
    conversation_transcript: str = "",
    ctx: Context | None = None,
) -> dict:
    state = WizardState(goal=goal, transcript=conversation_transcript)
    steps = get_wizard_steps()

    while state.current_step_index < len(steps):
        step = steps[state.current_step_index]

        if ctx:
            await ctx.info(f"Step: {step['id']}")

        prompt = step["instructions"].format(goal=state.goal)
        result_type = step["result_type"]

        result = await ctx.sample(
            messages=[
                {
                    "role": "system",
                    "content": "Follow the current wizard step and return structured output.",
                },
                {"role": "user", "content": prompt},
            ],
            tools=step.get("tools", []),
            result_type=result_type,
            temperature=0.2,
        )

        # Navigation
        if result.action == "cancel":
            return {"success": False, "message": "Cancelled by agent"}

        if result.action == "previous" and step.get("can_previous"):
            state.current_step_index = max(0, state.current_step_index - 1)
            continue

        if result.action == "skip" and step.get("can_skip"):
            state.current_step_index += 1
            continue

        # Store results based on step
        if step["id"] == "create_main_node" and isinstance(
            result, CreateMainNodeResult
        ):
            state.main_node = result.data

        elif step["id"] == "create_related_nodes" and isinstance(
            result, CreateRelatedNodesResult
        ):
            state.related_nodes.extend(result.data or [])

        elif step["id"] == "create_relationships" and isinstance(
            result, CreateRelationshipsResult
        ):
            state.relationships.extend(result.data or [])

        state.current_step_index += 1

    return {
        "success": True,
        "message": "Wizard finished",
        "main_node": state.main_node.model_dump() if state.main_node else None,
        "related_nodes": len(state.related_nodes),
        "relationships": len(state.relationships),
    }
