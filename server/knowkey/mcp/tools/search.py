"""
Tools: Search
=============
Intelligent search over the knowledge graph.
"""

from typing import Optional

from asgiref.sync import async_to_sync
from fastmcp.server.context import Context
from pydantic import Field

from knowkey.core.models import Node
from knowkey.mcp.core import serialize_node_list
from knowkey.mcp.server import mcp
from knowkey.mcp.utils import sync_to_async


@mcp.tool
@sync_to_async()
def search_nodes(
    query: str = Field(default="", description="Search term (title/summary/content)"),
    node_type_name: Optional[str] = Field(None, description="Filter by NodeType name"),
    tag_names: Optional[list[str]] = Field(None, description="Must have ALL these tags"),
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

    qs = Node.objects.select_related("node_type").prefetch_related("tags")

    if not include_all_versions:
        qs = qs.filter(version_of__isnull=True)

    if query:
        from django.db.models import Q
        qs = qs.filter(
            Q(title__icontains=query)
            | Q(summary__icontains=query)
            | Q(content__icontains=query)
        )

    if node_type_name:
        qs = qs.filter(node_type__name__iexact=node_type_name)

    if tag_names:
        for tag in tag_names:
            qs = qs.filter(tags__name__iexact=tag)

    qs = qs.distinct().order_by("-updated_at")[:limit]
    return serialize_node_list(list(qs))
