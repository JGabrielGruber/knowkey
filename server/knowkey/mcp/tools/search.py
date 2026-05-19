"""
Tools: Search
=============
Intelligent search over the knowledge graph.
"""

from typing import Optional

from asgiref.sync import async_to_sync
from fastmcp.server.context import Context
from pydantic import BaseModel, Field

from knowkey.core.models import Node
from knowkey.mcp.core import serialize_node_list
from knowkey.mcp.server import mcp
from knowkey.mcp.utils import sync_to_async


class SearchNodesInput(BaseModel):
    query: str = Field(
        default="",
        description="Search term to match against title, summary, or content. Leave empty to list recent nodes.",
    )
    node_type_name: Optional[str] = Field(
        default=None,
        description="Filter by exact NodeType name (e.g. 'Note', 'Decision', 'Question').",
    )
    tag_names: Optional[list[str]] = Field(
        default=None,
        description="Filter nodes that have ALL of these tags.",
    )
    limit: int = Field(
        default=10, ge=1, le=50, description="Maximum number of results."
    )
    include_all_versions: bool = Field(
        default=False,
        description="Set to true only if you specifically need historical snapshots. Usually keep false.",
    )


@mcp.tool
@sync_to_async()
def search_nodes(
    params: SearchNodesInput,
    ctx: Context = None,  # type: ignore
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
        async_to_sync(ctx.info)(f"Searching nodes with query='{params.query}'")

    qs = Node.objects.select_related("node_type").prefetch_related("tags")

    if not params.include_all_versions:
        qs = qs.filter(version_of__isnull=True)

    if params.query:
        from django.db.models import Q

        qs = qs.filter(
            Q(title__icontains=params.query)
            | Q(summary__icontains=params.query)
            | Q(content__icontains=params.query)
        )

    if params.node_type_name:
        qs = qs.filter(node_type__name__iexact=params.node_type_name)

    if params.tag_names:
        for tag in params.tag_names:
            qs = qs.filter(tags__name__iexact=tag)

    qs = qs.distinct().order_by("-updated_at")[: params.limit]
    return serialize_node_list(list(qs))
