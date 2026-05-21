"""
Knowkey MCP Server (Refactored)
===============================
Modern FastMCP 3.x implementation for Knowkey knowledge graph.

This server exposes Knowkey to AI agents (Grok, Claude, Cursor, etc.)
so they can explore, create, and connect knowledge autonomously.

Run with:
    python manage.py run_mcp_server --transport stdio
"""

import logging
import os
from contextlib import asynccontextmanager

import django
from fastmcp import FastMCP
from fastmcp.server.context import Context

logging.basicConfig(level=logging.DEBUG)

# =============================================================================
# Django Setup
# =============================================================================
if not os.environ.get("DJANGO_SETTINGS_MODULE"):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "knowkey.settings")

try:
    django.setup()
except Exception:
    pass  # Already configured when running via manage.py

# =============================================================================
# FastMCP Instance
# =============================================================================
mcp = FastMCP(
    name="Knowkey",
    instructions="""
You are connected to **Knowkey**, a versioned, graph-based knowledge base.

## Your Role
You are Knowkey's Knowledge Curator. Your goal is to help build a high-quality,
well-connected knowledge graph from conversations and research.

## Core Principles (Follow These Strictly)
1. **Search First** — Always use `search_nodes` before creating new knowledge.
2. **Quality over Quantity** — Create fewer, higher-quality nodes with excellent summaries.
3. **Respect Versioning** — Only create relationships between *live* (latest) nodes.
4. **Be Precise** — Use the correct NodeType and RelationshipType.
5. **Self-Correct** — Use history and revert tools when you make mistakes.

## Available Capabilities
- Explore ontology and existing knowledge via Resources
- Search, create, update, and link nodes via Tools
- Use specialized Prompts for complex knowledge extraction tasks

## Ontology Management
- Use `create_node_type` when existing types don't fit well.
- After creating a new type, you can immediately use it in `create_node`.

Work deliberately. Prefer creating strong connections over many weak ones.
""",
    version="0.2.0",  # Incremented for refactor
)


# =============================================================================
# Optional: Lifespan (for future async setup)
# =============================================================================
@asynccontextmanager
async def lifespan(app):
    # You can add startup/shutdown logic here if needed
    # (e.g., warm up caches, check DB connection)
    yield
    # Cleanup


# Note: FastMCP will use lifespan if passed during run in newer versions.
# For now we keep it simple.

# =============================================================================
# Import & Register Components
# =============================================================================
# We import after creating `mcp` so decorators can register on it.

# Resources
from knowkey.mcp.resources import ontology as ontology_resources  # noqa: F401

# Compose
from knowkey.mcp.compose import knowledge as knowledge_tool  # noqa: F401

# Prompts
from knowkey.mcp.prompts import knowledge as knowledge_prompts  # noqa: F401
from knowkey.mcp.resources import nodes as node_resources  # noqa: F401

# Tools
from knowkey.mcp.tools import nodes as node_tools  # noqa: F401
from knowkey.mcp.tools import relationships as relationship_tools  # noqa: F401
from knowkey.mcp.tools import search as search_tools  # noqa: F401

# =============================================================================
# Entry Point (for direct run)
# =============================================================================
if __name__ == "__main__":
    print("Starting Knowkey MCP Server (stdio transport recommended)...")
    mcp.run()
