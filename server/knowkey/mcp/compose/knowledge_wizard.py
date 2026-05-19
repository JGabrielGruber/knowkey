"""
compose/knowledge_wizard.py
===========================
Sequential Knowledge Wizard with per-step structured models.

This is an interactive, step-by-step compose tool that guides an agent
through high-quality knowledge ingestion into Knowkey.
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
    """Input model for creating or updating a node."""

    id: str | None = Field(
        default=None,
        description="If provided, the node will be updated. If null, a new node is created.",
    )
    title: str = Field(..., min_length=3, description="Clear and descriptive title")
    summary: str = Field(
        ..., min_length=10, description="High-quality 1-3 sentence summary"
    )
    node_type_name: str = Field(..., description="Exact name of an existing NodeType")
    content: str = Field(default="", description="Full content in Markdown")
    tag_names: list[str] = Field(default_factory=list, description="List of tag names")


class RelationshipInput(BaseModel):
    source_id: str
    target_id: str
    relationship_type: str
    weight: float = 1.0


# =============================================================================
# Per-Step Result Models (Structured Output)
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
# Smart Wrappers
# =============================================================================


async def create_or_update_node(node: NodeInput) -> dict:
    """Creates a new node or updates an existing one based on the presence of `id`."""
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
# Step Definitions
# =============================================================================


def get_wizard_steps() -> list[dict]:
    return [
        # Step 1: Main Node
        {
            "id": "create_main_node",
            "description": "Create or update the main/primary node",
            "instructions": (
                "Goal: {goal}\n\n"
                "1. Use search_nodes to check if similar knowledge already exists.\n"
                "2. Create or update the main node using create_or_update_node.\n"
                "3. If the NodeType doesn't exist, create it first with create_node_type."
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
        # Step 2: Related Nodes (batch)
        {
            "id": "create_related_nodes",
            "description": "Create or update related/correlated nodes (supports batch)",
            "instructions": (
                "Create or update supporting nodes that relate to the main node.\n"
                "You can provide multiple nodes at once."
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
        # Step 3: Relationships
        {
            "id": "create_relationships",
            "description": "Create relationships between the nodes",
            "instructions": (
                "Create meaningful relationships between the main node and related nodes.\n"
                "Use search_nodes if you need to find node IDs."
            ),
            "tools": [
                SamplingTool.from_function(w_search_nodes, name="search_nodes"),
            ],
            "result_type": CreateRelationshipsResult,
            "available_actions": ["create_relationships", "skip", "previous", "cancel"],
            "can_skip": True,
            "can_previous": True,
        },
        # Step 4: Review & Commit
        {
            "id": "review_and_commit",
            "description": "Review everything and confirm to persist",
            "instructions": (
                "Review the main node, related nodes, and relationships.\n"
                "Confirm only when everything looks correct."
            ),
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
    goal: str = Field(
        ...,
        description="High-level goal of this knowledge capture (e.g. 'Capture the key decisions and rationale from our discussion about authentication')",
    ),
    conversation_transcript: str = Field(
        default="",
        description="Optional full conversation transcript to extract knowledge from",
    ),
    ctx: Context | None = None,
) -> dict:
    """
    Interactive Knowledge Wizard for Knowkey.

    This is a **sequential, guided compose tool** that helps you build high-quality,
    well-connected knowledge in Knowkey step by step.

    It is designed for cases where you want to:
    - Extract knowledge from a conversation
    - Create or improve nodes with proper structure
    - Avoid duplication by searching first
    - Create meaningful relationships

    The wizard runs through 4 main phases:
    1. Create/Update the main node
    2. Create/Update related nodes (batch supported)
    3. Create relationships
    4. Final review and confirmation

    Use this tool when you want a structured, high-quality knowledge ingestion process
    instead of calling individual tools manually.
    """

    if ctx:
        await ctx.info(f"[Wizard] Starting knowledge_wizard | Goal: {goal}")

    state = WizardState(goal=goal, transcript=conversation_transcript)
    steps = get_wizard_steps()

    while state.current_step_index < len(steps):
        step = steps[state.current_step_index]
        step_id = step["id"]

        if ctx:
            await ctx.info(
                f"[Wizard] → Entering step: {step_id} ({step['description']})"
            )

        prompt = step["instructions"].format(goal=state.goal)
        result_type = step["result_type"]

        # Call sampling with structured output for this specific step
        result = await ctx.sample(
            messages=[
                {
                    "role": "system",
                    "content": "You are inside a sequential knowledge wizard. Follow the current step and return structured output.",
                },
                {"role": "user", "content": prompt},
            ],
            tools=step.get("tools", []),
            result_type=result_type,
            temperature=0.2,
        )

        if ctx:
            await ctx.info(
                f"[Wizard]   Received action: {result.action} in step {step_id}"
            )

        # ====================== Navigation ======================
        if result.action == "cancel":
            if ctx:
                await ctx.info("[Wizard] Wizard cancelled by agent.")
            return {"success": False, "message": "Wizard cancelled by agent."}

        if result.action == "previous" and step.get("can_previous"):
            if ctx:
                await ctx.info("[Wizard] Going back to previous step.")
            state.current_step_index = max(0, state.current_step_index - 1)
            continue

        if result.action == "skip" and step.get("can_skip"):
            if ctx:
                await ctx.info("[Wizard] Skipping current step.")
            state.current_step_index += 1
            continue

        # ====================== Store results ======================
        if step_id == "create_main_node" and isinstance(result, CreateMainNodeResult):
            state.main_node = result.data
            if ctx:
                await ctx.info(
                    f"[Wizard] Main node captured: {result.data.title if result.data else 'None'}"
                )

        elif step_id == "create_related_nodes" and isinstance(
            result, CreateRelatedNodesResult
        ):
            if result.data:
                state.related_nodes.extend(result.data)
            if ctx:
                await ctx.info(
                    f"[Wizard] Related nodes added: {len(result.data or [])}"
                )

        elif step_id == "create_relationships" and isinstance(
            result, CreateRelationshipsResult
        ):
            if result.data:
                state.relationships.extend(result.data)
            if ctx:
                await ctx.info(
                    f"[Wizard] Relationships proposed: {len(result.data or [])}"
                )

        # Move to next step
        state.current_step_index += 1

    if ctx:
        await ctx.info("[Wizard] Wizard completed all steps.")

    return {
        "success": True,
        "message": "Knowledge wizard finished successfully.",
        "goal": state.goal,
        "main_node": state.main_node.model_dump() if state.main_node else None,
        "related_nodes_count": len(state.related_nodes),
        "relationships_count": len(state.relationships),
        "steps_completed": state.current_step_index,
    }
