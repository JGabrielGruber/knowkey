"""
compose/knowledge.py
====================
Improved multi-turn Knowledge Composition Tool (stateful).

Latest improvements:
- Stronger tags support (auto-adds "source:compose")
- Better guidance with realistic examples
- Improved error messages for relationship types
"""

import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

import redis
from django.conf import settings
from fastmcp.server.context import Context
from knowkey.core.models import NodeType, RelationshipType
from knowkey.mcp.core import (
    create_node,
    create_node_type,
    create_relationship,
    create_relationship_type,
    search_nodes,
    update_node,
)
from knowkey.mcp.server import mcp
from knowkey.mcp.utils import clean_inputs, sanitize_name, sync_to_async
from pydantic import BaseModel, Field, field_validator

# =============================================================================
# Redis Session
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
# Input Models
# =============================================================================
class NodeInput(BaseModel):
    id: str | None = Field(
        default=None, description="Node ID to update (None = create new)"
    )
    title: str = Field(..., min_length=3)
    summary: str = Field(..., min_length=10)
    node_type_name: str
    content: str = ""
    tag_names: list[str] = Field(default_factory=list)


class RelationshipInput(BaseModel):
    source_id: str | None = None
    source_node_id: str | None = None
    target_id: str | None = None
    target_node_id: str | None = None

    relationship_type_name: str
    weight: float = 1.0

    @field_validator("source_id", "target_id", mode="before")
    @classmethod
    def normalize_ids(cls, v, info):
        if v is None:
            alias = (
                "source_node_id" if info.field_name == "source_id" else "target_node_id"
            )
            return info.data.get(alias)
        return v


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

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ComposeState":
        return cls(**data)

    def get_progress(self) -> str:
        main = "✅" if self.main_node else "⏳"
        return f"Main: {main} | Related: {len(self.related_nodes)} | Relationships: {len(self.relationships)}"


# =============================================================================
# Core Helpers
# =============================================================================
@sync_to_async()
def do_search_nodes(query: str = "", limit: int = 8):
    nodes = search_nodes(query=query, limit=limit)
    return [
        {
            "id": str(n.id),
            "title": n.title,
            "summary": n.summary,
            "node_type": n.node_type.name,
        }
        for n in nodes
    ]


@sync_to_async()
def do_create_node_type(
    name: str, description: str = "", icon: str = "", color: str = ""
):
    nt = create_node_type(name=name, description=description, icon=icon, color=color)
    return {"success": True, "name": nt.name, "id": str(nt.id)}


@sync_to_async()
def do_create_relationship_type(
    name: str, description: str = "", icon: str = "", color: str = ""
):
    rt = create_relationship_type(
        name=name, description=description, icon=icon, color=color
    )
    return {"success": True, "name": rt.name, "id": str(rt.id)}


@sync_to_async()
def do_create_or_update_node(node_input: NodeInput):
    """Auto-create NodeType + default tags"""

    create_node_type(name=node_input.node_type_name)

    # Auto-add source tag
    if not node_input.tag_names:
        node_input.tag_names = ["source:compose"]

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
def do_create_relationship(relationship: RelationshipInput):
    source_id = relationship.source_id or relationship.source_node_id
    target_id = relationship.target_id or relationship.target_node_id

    if not source_id or not target_id:
        raise ValueError("Both source and target IDs are required")

    create_relationship_type(name=relationship.relationship_type_name)

    create_relationship(
        source_id=source_id,
        target_id=target_id,
        relationship_type_name=relationship.relationship_type_name,
        weight=relationship.weight,
    )
    return {"success": True}


# =============================================================================
# Steps + Guidance
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
            "can_continue": lambda s: s.main_node is not None,
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
            "can_continue": lambda s: True,
            "can_previous": True,
        },
        {
            "id": "create_relationships",
            "title": "3. Relationships",
            "description": "Connect nodes with meaningful relationships",
            "allowed_actions": [
                "search_nodes",
                "create_relationship_type",
                "add_relationship",
                "continue",
                "previous",
                "cancel",
            ],
            "can_continue": lambda s: True,
            "can_previous": True,
        },
        {
            "id": "review_and_commit",
            "title": "4. Review & Commit",
            "description": "Review everything and finish",
            "allowed_actions": ["confirm", "previous", "cancel"],
            "can_continue": lambda s: False,
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
    action: str = Field("", description="Action to perform"),
    data: dict | None = Field(default=None, description="Data for the action"),
    ctx: Context | None = None,
) -> dict:
    """Stateful guided multi-turn knowledge composition tool."""

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
            await ctx.info(f"[compose] New session: {session_id}")

    steps = get_steps()
    current_step = steps[state.current_step_index]

    if ctx:
        await ctx.info(
            f"[compose] Step {state.current_step_index + 1}/4 — {current_step['id']}"
        )

    # Navigation
    if action == "cancel":
        delete_session(session_id)
        return {"success": True, "message": "Session cancelled."}

    if action == "previous" and current_step.get("can_previous"):
        state.current_step_index = max(0, state.current_step_index - 1)
        save_session(session_id, state.to_dict())
        return _build_response(
            session_id,
            state,
            steps[state.current_step_index],
            "Moved to previous step.",
        )

    if action == "continue":
        if not current_step.get("can_continue", lambda s: True)(state):
            return _build_response(
                session_id,
                state,
                current_step,
                "Cannot continue yet — complete current step first.",
                error=True,
            )
        state.current_step_index = min(len(steps) - 1, state.current_step_index + 1)
        save_session(session_id, state.to_dict())
        return _build_response(
            session_id,
            state,
            steps[state.current_step_index],
            f"Advanced to {steps[state.current_step_index]['title']}",
        )

    # Step actions
    result = None
    message = ""

    try:
        if action == "search_nodes":
            result = await do_search_nodes(**(data or {}))
            message = "Search completed."

        elif action == "create_node_type":
            result = await do_create_node_type(**(data or {}))
            message = "NodeType ready."

        elif action == "create_relationship_type":
            result = await do_create_relationship_type(**(data or {}))
            message = "RelationshipType ready."

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
            message = f"✅ Relationship created: {rel_input.relationship_type_name}"

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
                f"Action '{action}' not available in this step.",
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
            f"Progress: {progress}\n"
            f"You are in: **{current_step['title']}**\n\n"
            "Recommended actions:\n"
            "• search_nodes → find existing knowledge\n"
            "• set_main_node / add_related_node → include tag_names if useful\n"
            "• add_relationship → use only valid types from ontology\n\n"
            "Example for current step:\n"
            "{'title': 'Gabe Newell', 'summary': '...', 'node_type_name': 'Person', 'tag_names': ['founder', 'valve']}"
        ),
    }
