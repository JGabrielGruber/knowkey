"""
compose/knowledge.py
====================
Improved multi-turn Knowledge Composition Tool.

Now features:
- Explicit per-step actions
- "continue" action to advance steps
- Very transparent state + guidance for the agent
- Strict but friendly flow
"""

import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import redis
from django.conf import settings
from fastmcp.server.context import Context
from knowkey.mcp.core import (
    create_node,
    create_node_type,
    create_relationship,
    search_nodes,
    update_node,
)
from knowkey.mcp.server import mcp
from knowkey.mcp.utils import clean_inputs, sync_to_async
from pydantic import BaseModel, Field

# =============================================================================
# Redis Session
# =============================================================================
REDIS_URL = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
r = redis.from_url(REDIS_URL, decode_responses=True)


def _session_key(session_id: str) -> str:
    return f"knowkey:compose_knowledge:{session_id}"


def create_session(state: dict) -> str:
    session_id = str(uuid.uuid4())
    r.setex(_session_key(session_id), 3600, json.dumps(state))  # 1h TTL
    return session_id


def load_session(session_id: str) -> dict | None:
    data = r.get(_session_key(session_id))
    return json.loads(data) if data else None


def save_session(session_id: str, state: dict):
    r.setex(_session_key(session_id), 3600, json.dumps(state))


def delete_session(session_id: str):
    r.delete(_session_key(session_id))


# =============================================================================
# Models
# =============================================================================
class NodeInput(BaseModel):
    id: str | None = Field(
        default=None, description="Node ID to update, or None to create new"
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


@dataclass
class ComposeState:
    goal: str
    transcript: str = ""
    current_step_index: int = 0
    main_node: dict | None = None  # final NodeInput dict
    related_nodes: list[dict] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ComposeState":
        return cls(**data)

    def get_progress(self) -> str:
        main = "✅" if self.main_node else "⏳"
        rel = len(self.related_nodes)
        rels = len(self.relationships)
        return f"Main: {main} | Related nodes: {rel} | Relationships: {rels}"


# =============================================================================
# Core Action Helpers (async-safe)
# =============================================================================
@sync_to_async()
def do_search_nodes(query: str = "", limit: int = 8):
    nodes = search_nodes(query=query, limit=limit)
    return [{"id": str(n.id), "title": n.title, "summary": n.summary} for n in nodes]


@sync_to_async()
def do_create_node_type(name: str, description: str = "", icon: str = ""):
    nt = create_node_type(name=name, description=description, icon=icon)
    return {"success": True, "name": nt.name, "id": str(nt.id)}


@sync_to_async()
def do_create_or_update_node(node_input: NodeInput):
    if node_input.id:
        node = update_node(
            node_id=node_input.id,
            title=node_input.title,
            summary=node_input.summary,
            content=node_input.content,
            node_type_name=node_input.node_type_name,
            tag_names=node_input.tag_names,
        )
    else:
        node = create_node(
            title=node_input.title,
            summary=node_input.summary,
            node_type_name=node_input.node_type_name,
            content=node_input.content,
            tag_names=node_input.tag_names,
        )
    return {
        "success": True,
        "id": str(node.id),
        "title": node.title,
        "version_number": node.version_number,
    }


@sync_to_async()
def do_create_relationship(rel: RelationshipInput):
    create_relationship(
        source_id=rel.source_id,
        target_id=rel.target_id,
        relationship_type=rel.relationship_type,
        weight=rel.weight,
    )
    return {"success": True}


# =============================================================================
# Step Configuration
# =============================================================================
def get_steps() -> list[dict]:
    return [
        {
            "id": "create_main_node",
            "title": "1. Main Node",
            "description": "Create or update the primary knowledge node",
            "allowed_actions": [
                "search_nodes",
                "create_node_type",
                "set_main_node",
                "continue",
                "cancel",
            ],
            "can_continue": lambda state: state.main_node is not None,
            "can_previous": False,
        },
        {
            "id": "create_related_nodes",
            "title": "2. Related Nodes",
            "description": "Add supporting / related nodes",
            "allowed_actions": [
                "search_nodes",
                "create_node_type",
                "add_related_node",
                "continue",
                "previous",
                "cancel",
            ],
            "can_continue": lambda state: True,  # optional
            "can_previous": True,
        },
        {
            "id": "create_relationships",
            "title": "3. Relationships",
            "description": "Connect nodes with meaningful relationships",
            "allowed_actions": [
                "search_nodes",
                "add_relationship",
                "continue",
                "previous",
                "cancel",
            ],
            "can_continue": lambda state: True,
            "can_previous": True,
        },
        {
            "id": "review_and_commit",
            "title": "4. Review & Commit",
            "description": "Review everything and finish",
            "allowed_actions": ["confirm", "previous", "cancel"],
            "can_continue": lambda state: False,
            "can_previous": True,
        },
    ]


# =============================================================================
# Main Tool
# =============================================================================
@mcp.tool
@clean_inputs
async def compose_knowledge(
    goal: str = Field(
        default="", description="High-level goal (required on first call)"
    ),
    session_id: str | None = Field(
        default=None, description="Session ID from previous response"
    ),
    action: str = Field(
        default="",
        description="Action to perform: search_nodes, set_main_node, add_related_node, add_relationship, continue, previous, cancel, confirm...",
    ),
    data: dict | None = Field(default=None, description="Data payload for the action"),
    ctx: Context | None = None,
) -> dict:
    """Stateful, guided multi-turn knowledge composition tool with explicit flow."""

    # ── Load / Create session ─────────────────────────────────────
    if session_id:
        state_dict = load_session(session_id)
        if not state_dict:
            return {"success": False, "error": "Invalid or expired session_id"}
        state = ComposeState.from_dict(state_dict)
    else:
        if not goal.strip():
            return {"success": False, "error": "goal is required on first call"}
        state = ComposeState(goal=goal)
        session_id = create_session(state.to_dict())
        if ctx:
            await ctx.info(f"[compose] New session created: {session_id}")

    steps = get_steps()
    current_step = steps[state.current_step_index]

    if ctx:
        await ctx.info(
            f"[compose] Step {state.current_step_index+1}/4 — {current_step['id']}"
        )

    # ── Handle navigation / special actions first ─────────────────
    if action == "cancel":
        delete_session(session_id)
        return {"success": True, "message": "Session cancelled."}

    if action == "previous" and current_step.get("can_previous"):
        state.current_step_index = max(0, state.current_step_index - 1)
        save_session(session_id, state.to_dict())
        new_step = steps[state.current_step_index]
        return _build_response(session_id, state, new_step, "Moved to previous step.")

    if action == "continue":
        if not current_step.get("can_continue", lambda s: True)(state):
            return _build_response(
                session_id,
                state,
                current_step,
                "Cannot continue yet — please complete the current step first (e.g. create main node).",
                error=True,
            )
        state.current_step_index = min(len(steps) - 1, state.current_step_index + 1)
        save_session(session_id, state.to_dict())
        new_step = steps[state.current_step_index]
        return _build_response(
            session_id, state, new_step, f"✅ Advanced to step: {new_step['title']}"
        )

    # ── Step-specific actions ─────────────────────────────────────
    result = None
    message = ""

    try:
        if action == "search_nodes":
            result = await do_search_nodes(**(data or {}))
            message = "Search results returned."

        elif action == "create_node_type":
            result = await do_create_node_type(**(data or {}))
            message = "NodeType created (or already existed)."

        elif action == "set_main_node" and current_step["id"] == "create_main_node":
            node_input = NodeInput(**data)
            result = await do_create_or_update_node(node_input)
            state.main_node = node_input.model_dump()
            message = f"✅ Main node set: {node_input.title}"

        elif (
            action == "add_related_node"
            and current_step["id"] == "create_related_nodes"
        ):
            node_input = NodeInput(**data)
            result = await do_create_or_update_node(node_input)
            state.related_nodes.append(node_input.model_dump())
            message = f"✅ Related node added: {node_input.title}"

        elif (
            action == "add_relationship"
            and current_step["id"] == "create_relationships"
        ):
            rel_input = RelationshipInput(**data)
            result = await do_create_relationship(rel_input)
            state.relationships.append(rel_input.model_dump())
            message = f"✅ Relationship created: {rel_input.relationship_type}"

        elif action == "confirm" and current_step["id"] == "review_and_commit":
            delete_session(session_id)
            return {
                "success": True,
                "message": "🎉 Knowledge composition completed and committed!",
                "final_state": state.to_dict(),
            }

        else:
            return _build_response(
                session_id,
                state,
                current_step,
                f"Action '{action}' not supported in step '{current_step['id']}'",
                error=True,
            )

        save_session(session_id, state.to_dict())

    except Exception as e:
        return _build_response(
            session_id, state, current_step, f"Error: {str(e)}", error=True
        )

    return _build_response(session_id, state, current_step, message, result=result)


def _build_response(
    session_id: str,
    state: ComposeState,
    current_step: dict,
    message: str,
    result: Any = None,
    error: bool = False,
) -> dict:
    """Build rich, transparent response for the agent."""
    progress = state.get_progress()

    return {
        "success": not error,
        "session_id": session_id,
        "current_step": current_step["id"],
        "step_title": current_step["title"],
        "step_description": current_step["description"],
        "progress": progress,
        "draft_state": {
            "main_node": state.main_node,
            "related_nodes_count": len(state.related_nodes),
            "relationships_count": len(state.relationships),
        },
        "allowed_actions": current_step["allowed_actions"],
        "message": message,
        "result": result,
        "guidance": (
            f"Current progress: {progress}\n"
            f"You are in step '{current_step['title']}'. "
            f"Use one of the allowed_actions above. "
            f"When ready, call action='continue' to move forward."
        ),
    }
