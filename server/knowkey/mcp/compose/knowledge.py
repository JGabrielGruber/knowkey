"""
compose/knowledge.py
====================
Multi-turn Knowledge Composition Tool (compose_knowledge)

This is a stateful, back-and-forth compose tool designed to help agents
build high-quality, connected knowledge in Knowkey across multiple turns.

It uses Redis to persist session state between calls.

How it works:
-------------
1. First call: Provide `goal` (and optionally a transcript). A new session is created.
2. The tool returns the current step, available actions, and current state.
3. Agent chooses an action (navigation or tool action) and calls the tool again with `session_id`.
4. Repeat until the agent confirms in the final step.
5. On confirmation, nodes and relationships are persisted.

This tool helps the agent manage state and follow a structured high-quality process.
"""

import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import redis
from django.conf import settings
from fastmcp.server.context import Context
from knowkey.mcp.server import mcp
from knowkey.mcp.utils import sync_to_async
from pydantic import BaseModel, Field

# =============================================================================
# Redis Configuration
# =============================================================================
REDIS_URL = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
r = redis.from_url(REDIS_URL, decode_responses=True)


def _session_key(session_id: str) -> str:
    return f"knowkey:compose_knowledge:{session_id}"


def create_session(state: dict) -> str:
    session_id = str(uuid.uuid4())
    key = _session_key(session_id)
    r.setex(key, 3600, json.dumps(state))  # 1 hour TTL
    return session_id


def load_session(session_id: str) -> dict | None:
    try:
        key = _session_key(session_id)
        data = r.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        print(e)
        return None


def save_session(session_id: str, state: dict) -> None:
    key = _session_key(session_id)
    r.setex(key, 3600, json.dumps(state))


def delete_session(session_id: str) -> None:
    r.delete(_session_key(session_id))


# =============================================================================
# Input Models
# =============================================================================


class NodeInput(BaseModel):
    """Can be used to create or update a node."""

    id: str | None = Field(
        default=None, description="If provided → update. If null → create new node."
    )
    title: str = Field(..., min_length=3)
    summary: str = Field(..., min_length=10)
    node_type_name: str
    content: str = ""
    tag_names: list[str] = Field(default_factory=list)


class RelationshipInput(BaseModel):
    source_id: str
    target_id: str
    relationship_type: str
    weight: float = 1.0


# =============================================================================
# State
# =============================================================================


@dataclass
class ComposeState:
    goal: str
    transcript: str = ""
    current_step_index: int = 0
    main_node: dict | None = None
    related_nodes: list[dict] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)
    created_node_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ComposeState":
        return cls(**data)


# =============================================================================
# Wrapped Tool Actions (exposed as actions the agent can choose)
# =============================================================================


async def action_search_nodes(query: str, limit: int = 8) -> dict:
    from knowkey.mcp.tools.search import search_nodes

    return await search_nodes(
        query=query,
        node_type_name=None,
        tag_names=None,
        limit=limit,
        include_all_versions=None,
    )


async def action_create_node_type(
    name: str, description: str = "", icon: str = ""
) -> dict:
    from knowkey.mcp.tools.nodes import create_node_type

    return await create_node_type(
        name=name, description=description, icon=icon, color=""
    )


async def action_create_or_update_node(node: NodeInput) -> dict:
    if node.id:
        from knowkey.mcp.tools.nodes import update_node

        return await update_node(
            node_id=node.id,
            title=node.title,
            summary=node.summary,
            content=node.content,
            node_type_name=node.node_type_name,
            metadata=None,
            author_name=None,
            tag_names=node.tag_names,
        )
    else:
        from knowkey.mcp.tools.nodes import create_node

        return await create_node(
            title=node.title,
            summary=node.summary,
            node_type_name=node.node_type_name,
            content=node.content,
            metadata=None,
            author_name=None,
            tag_names=node.tag_names,
        )


# =============================================================================
# Step Definitions
# =============================================================================


def get_steps() -> list[dict]:
    return [
        {
            "id": "create_main_node",
            "description": "Create or update the main node",
            "available_actions": [
                {"name": "search_nodes", "description": "Search existing knowledge"},
                {
                    "name": "create_node_type",
                    "description": "Create a new NodeType if needed",
                },
                {
                    "name": "create_or_update_node",
                    "description": "Create or update the main node",
                },
                {"name": "skip", "description": "Skip this step (not recommended)"},
                {"name": "cancel", "description": "Cancel the whole process"},
            ],
            "can_skip": False,
            "can_previous": False,
        },
        {
            "id": "create_related_nodes",
            "description": "Create or update related nodes (batch supported)",
            "available_actions": [
                {"name": "search_nodes", "description": "Search existing knowledge"},
                {"name": "create_node_type", "description": "Create a new NodeType"},
                {
                    "name": "create_or_update_node",
                    "description": "Create or update a related node",
                },
                {"name": "skip", "description": "Skip creating related nodes"},
                {"name": "previous", "description": "Go back to previous step"},
                {"name": "cancel", "description": "Cancel"},
            ],
            "can_skip": True,
            "can_previous": True,
        },
        {
            "id": "create_relationships",
            "description": "Create relationships between nodes",
            "available_actions": [
                {"name": "search_nodes", "description": "Find node IDs if needed"},
                {"name": "skip", "description": "Skip creating relationships"},
                {"name": "previous", "description": "Go back"},
                {"name": "cancel", "description": "Cancel"},
            ],
            "can_skip": True,
            "can_previous": True,
        },
        {
            "id": "review_and_commit",
            "description": "Review and persist everything",
            "available_actions": [
                {
                    "name": "confirm",
                    "description": "Persist all nodes and relationships",
                },
                {"name": "previous", "description": "Go back to make changes"},
                {"name": "cancel", "description": "Cancel"},
            ],
            "can_skip": False,
            "can_previous": True,
        },
    ]


# =============================================================================
# Main Tool: compose_knowledge
# =============================================================================


@mcp.tool
async def compose_knowledge(
    goal: str = Field(
        default="",
        description="High-level goal of this knowledge session (required on first call)",
    ),
    session_id: str | None = Field(
        default=None,
        description="Session ID from previous response. Omit on first call to start a new session.",
    ),
    action: str | None = Field(
        default=None,
        description="Action to perform in the current step (e.g. create_or_update_node, search_nodes, confirm, skip, previous, cancel)",
    ),
    data: dict | None = Field(
        default=None,
        description="Data for the chosen action (e.g. NodeInput when using create_or_update_node)",
    ),
    ctx: Context | None = None,
) -> dict:
    """
    Multi-turn Knowledge Composition Tool.

    This is a **stateful compose tool** meant to be called multiple times.
    It guides you through a high-quality 4-step process to create well-structured,
    connected knowledge in Knowkey.

    ## Expected Interaction Flow

    1. **First call** — Provide only `goal` (and optionally a transcript).
       → Tool creates a session and returns step 1 + available actions.

    2. **Subsequent calls** — Always send:
       - `session_id`
       - `action` (one of the available actions in current step)
       - `data` when the action requires it (e.g. when creating a node)

    3. Continue until you reach **review_and_commit** and choose `confirm`.

    On confirmation, the tool will create/update nodes and relationships.

    This tool is especially useful when you want structured guidance and
    state management across multiple interactions.
    """

    # ------------------------------------------------------------------
    # Load or create session
    # ------------------------------------------------------------------
    if session_id:
        state_dict = load_session(session_id)
        if not state_dict:
            return {"success": False, "error": "Invalid or expired session_id"}
        try:
            print("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
            print(state_dict)
            state = ComposeState.from_dict(state_dict)
        except Exception as e:
            print(e)
            return {}
    else:
        if not goal:
            return {
                "success": False,
                "error": "goal is required when starting a new session",
            }

        state = ComposeState(goal=goal)
        session_id = create_session(state.to_dict())
        if ctx:
            await ctx.info(f"[compose_knowledge] New session created: {session_id}")

    steps = get_steps()
    current_step = steps[state.current_step_index]

    # ------------------------------------------------------------------
    # If no action yet (first call or just showing state)
    # ------------------------------------------------------------------
    if not action:
        return {
            "success": True,
            "session_id": session_id,
            "current_step": current_step["id"],
            "step_description": current_step["description"],
            "message": f"Welcome to step '{current_step['id']}'. Please choose an action from the list below.",
            "available_actions": current_step["available_actions"],
            "state": state.to_dict(),
            "next_expected": "Send session_id + action (and data if required by the action)",
        }

    # ------------------------------------------------------------------
    # Handle navigation actions
    # ------------------------------------------------------------------
    if action == "cancel":
        delete_session(session_id)
        return {"success": True, "message": "Session cancelled."}

    if action == "previous" and current_step.get("can_previous"):
        state.current_step_index = max(0, state.current_step_index - 1)
        save_session(session_id, state.to_dict())
        new_step = steps[state.current_step_index]
        return {
            "success": True,
            "session_id": session_id,
            "current_step": new_step["id"],
            "message": "Moved back to the previous step.",
            "available_actions": new_step["available_actions"],
            "state": state.to_dict(),
        }

    if action == "skip" and current_step.get("can_skip"):
        state.current_step_index += 1
        save_session(session_id, state.to_dict())
        new_step = steps[state.current_step_index]
        return {
            "success": True,
            "session_id": session_id,
            "current_step": new_step["id"],
            "message": "Step skipped.",
            "available_actions": new_step["available_actions"],
            "state": state.to_dict(),
        }

    # ------------------------------------------------------------------
    # Execute step-specific actions
    # ------------------------------------------------------------------
    step_id = current_step["id"]

    if step_id == "create_main_node" and action == "create_or_update_node":
        if not data:
            return {
                "success": False,
                "error": "data is required for create_or_update_node",
            }

        try:
            node_input = NodeInput(**data)
            result = await action_create_or_update_node(node_input)
            state.main_node = node_input.model_dump()
            save_session(session_id, state.to_dict())

            return {
                "success": True,
                "session_id": session_id,
                "current_step": step_id,
                "message": "Main node created/updated successfully.",
                "result": result,
                "state": state.to_dict(),
            }
        except Exception as e:
            return {
                "success": False,
                "session_id": session_id,
                "error": f"Failed to create/update node: {str(e)}",
                "state": state.to_dict(),
            }

    if action in ["search_nodes", "create_node_type"]:
        # These are read/create helpers — we just execute them
        if action == "search_nodes":
            result = await action_search_nodes(data.get("query", "") if data else "")
        else:
            result = await action_create_node_type(
                data.get("name", ""), data.get("description", ""), data.get("icon", "")
            )
        ret = {
            "success": True,
            "session_id": session_id,
            "message": f"Executed {action}",
            "result": result,
            "state": state.to_dict(),
        }
        return ret

    # TODO: Add handling for related nodes and relationships in next iterations
    if step_id in ["create_related_nodes", "create_relationships"]:
        # For now we just advance or store simple data
        if action == "create_or_update_node" and data:
            node_input = NodeInput(**data)
            state.related_nodes.append(node_input.model_dump())
            save_session(session_id, state.to_dict())
            return {
                "success": True,
                "session_id": session_id,
                "message": "Related node added to draft.",
                "state": state.to_dict(),
            }

    # ------------------------------------------------------------------
    # Final step: Persist everything
    # ------------------------------------------------------------------
    if step_id == "review_and_commit" and action == "confirm":
        # TODO: Actually persist using create_or_update_node + create_relationship
        # For now we just mark as done
        if ctx:
            await ctx.info("[compose_knowledge] Committing knowledge...")

        # Placeholder: In next version we will actually create the nodes here
        delete_session(session_id)

        return {
            "success": True,
            "message": "Knowledge committed successfully (persistence logic pending full implementation).",
            "state": state.to_dict(),
        }

    # Default fallback - always return consistent structure
    return {
        "success": False,
        "session_id": session_id,
        "current_step": step_id,
        "error": f"Action '{action}' is not supported or not yet implemented in step '{step_id}'",
        "available_actions": current_step.get("available_actions", []),
        "state": state.to_dict(),
        "message": "Please choose one of the available actions for the current step.",
    }
