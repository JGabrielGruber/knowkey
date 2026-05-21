"""
Tools: Search
=============
Intelligent search over the knowledge graph.
"""

from typing import Optional

from asgiref.sync import async_to_sync
from fastmcp.server.context import Context
from knowkey.core.models import Node
from knowkey.mcp.core import search_nodes as core_search_nodes
from knowkey.mcp.core import serialize_node_list
from knowkey.mcp.server import mcp
from knowkey.mcp.utils import sync_to_async
from pydantic import Field


@mcp.tool
@sync_to_async()
def search_nodes(
    query: str = Field(default="", description="Search term (title/summary/content)"),
    node_type_name: Optional[str] = Field(None, description="Filter by NodeType name"),
    tag_names: Optional[list[str]] = Field(
        None, description="Must have ALL these tags"
    ),
    limit: int = Field(default=10, ge=1, le=50),
    include_all_versions: bool = Field(default=False, description="Usually keep False"),
    ctx: Context | None = None,
) -> list[dict]:
    """
    Search for nodes in Knowkey.

    ## When to use
    - ALWAYS call this before creating new knowledge.
    - Use to find existing relevant nodes to link to.
    - Use to understand what knowledge already exists on a topic.

    ## Important
    - By default returns only **live** (latest) versions.
    - Results are ordered by most recently updated.
    """
    if ctx:
        async_to_sync(ctx.info)(f"Searching: '{query}'")

    nodes = core_search_nodes(
        query=query,
        node_type_name=node_type_name,
        tag_names=tag_names,
        limit=limit,
        include_all_versions=include_all_versions,
    )
    return serialize_node_list(nodes=nodes)
