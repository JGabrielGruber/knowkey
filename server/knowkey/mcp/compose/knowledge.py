"""
compose/knowledge.py
====================
Multi-turn Knowledge Composition Tool (stateful).

Now uses core.py directly instead of calling other tools.
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
from knowkey.mcp.utils import sync_to_async
from pydantic import BaseModel, Field

# =============================================================================
# Redis Session Management
# =============================================================================

REDIS_URL = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
r = redis.from_url(REDIS_URL, decode_responses=True)


def _session_key(session_id: str) -> str:
    return f"knowkey:compose_knowledge:{session_id}"


def create_session(state: dict) -> str:
    session_id = str(uuid.uuid4())
    r.setex(_session_key(session_id), 3600, json.dumps(state))
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
    id: str | None = None
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
    main_node: dict | None = None
    related_nodes: list[dict] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ComposeState":
        return cls(**data)


# =============================================================================
# Core Action Helpers
# =============================================================================


@sync_to_async()
def action_search_nodes(query: str = "", limit: int = 8):
    nodes = search_nodes(query=query, limit=limit)
    return [{"id": str(n.id), "title": n.title, "summary": n.summary} for n in nodes]


@sync_to_async()
def action_create_node_type(name: str, description: str = "", icon: str = ""):
    nt = create_node_type(name=name, description=description, icon=icon)
    return {"success": True, "name": nt.name, "id": str(nt.id)}


@sync_to_async()
def action_create_or_update_node(node: NodeInput):
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
        "version": result.version_number,
    }


@sync_to_async()
def action_create_relationship(rel: RelationshipInput):
    create_relationship(
        source_id=rel.source_id,
        target_id=rel.target_id,
        relationship_type=rel.relationship_type,
        weight=rel.weight,
    )
    return {"success": True}


# =============================================================================
# Steps
# =============================================================================


def get_steps() -> list[dict]:
    return [
        {
            "id": "create_main_node",
            "description": "Create or update the main node",
            "available_actions": [
                "search_nodes",
                "create_node_type",
                "create_or_update_node",
                "skip",
                "cancel",
            ],
            "can_skip": False,
            "can_previous": False,
        },
        {
            "id": "create_related_nodes",
            "description": "Create related nodes",
            "available_actions": [
                "search_nodes",
                "create_node_type",
                "create_or_update_node",
                "skip",
                "previous",
                "cancel",
            ],
            "can_skip": True,
            "can_previous": True,
        },
        {
            "id": "create_relationships",
            "description": "Create relationships",
            "available_actions": [
                "search_nodes",
                "create_relationship",
                "skip",
                "previous",
                "cancel",
            ],
            "can_skip": True,
            "can_previous": True,
        },
        {
            "id": "review_and_commit",
            "description": "Review and commit",
            "available_actions": ["confirm", "previous", "cancel"],
            "can_skip": False,
            "can_previous": True,
        },
    ]


# =============================================================================
# Main Tool
# =============================================================================


@mcp.tool
async def compose_knowledge(
    goal: str = Field(default="", description="Goal (required on first call)"),
    session_id: str | None = Field(default=None, description="Session ID"),
    action: str | None = Field(default=None),
    data: dict | None = Field(default=None),
    ctx: Context | None = None,
) -> dict:
    """Multi-turn stateful knowledge composition tool."""

    # Load or create session
    if session_id:
        state_dict = load_session(session_id)
        if not state_dict:
            return {"success": False, "error": "Invalid session"}
        state = ComposeState.from_dict(state_dict)
    else:
        if not goal:
            return {"success": False, "error": "goal is required"}
        state = ComposeState(goal=goal)
        session_id = create_session(state.to_dict())

    steps = get_steps()
    current_step = steps[state.current_step_index]

    if not action:
        return {
            "success": True,
            "session_id": session_id,
            "current_step": current_step["id"],
            "available_actions": current_step["available_actions"],
            "state": state.to_dict(),
        }

    # Navigation
    if action == "cancel":
        delete_session(session_id)
        return {"success": True, "message": "Cancelled"}

    if action == "previous" and current_step.get("can_previous"):
        state.current_step_index = max(0, state.current_step_index - 1)
        save_session(session_id, state.to_dict())
        return {
            "success": True,
            "session_id": session_id,
            "current_step": steps[state.current_step_index]["id"],
        }

    if action == "skip" and current_step.get("can_skip"):
        state.current_step_index += 1
        save_session(session_id, state.to_dict())
        return {
            "success": True,
            "session_id": session_id,
            "current_step": steps[state.current_step_index]["id"],
        }

    # Actions
    try:
        if action == "search_nodes":
            result = await action_search_nodes(**(data or {}))
        elif action == "create_node_type":
            result = await action_create_node_type(**(data or {}))
        elif action == "create_or_update_node":
            node_input = NodeInput(**data)
            result = await action_create_or_update_node(node_input)
            if state.current_step_index == 0:
                state.main_node = node_input.model_dump()
            else:
                state.related_nodes.append(node_input.model_dump())
        elif action == "create_relationship":
            rel_input = RelationshipInput(**data)
            result = await action_create_relationship(rel_input)
            state.relationships.append(rel_input.model_dump())
        elif action == "confirm" and current_step["id"] == "review_and_commit":
            # Final commit (already persisted incrementally)
            delete_session(session_id)
            return {"success": True, "message": "Knowledge successfully committed."}
        else:
            result = None

        save_session(session_id, state.to_dict())

        return {
            "success": True,
            "session_id": session_id,
            "current_step": current_step["id"],
            "result": result,
            "state": state.to_dict(),
        }

    except Exception as e:
        return {"success": False, "error": str(e), "session_id": session_id}
