import asyncio
from typing import Any

from django.test import TestCase
from fastmcp import Client

from knowkey.core.models import (
    Author,
    AuthorType,
    Node,
    NodeType,
    RelationshipType,
)
from knowkey.mcp.server import mcp
from knowkey.mcp.utils import async_to_sync


class MCPTestCase(TestCase):
    """Base class with common setup and MCP helpers."""

    @classmethod
    def setUpTestData(cls):
        cls.author = Author.objects.create(
            name="Test User", author_type=AuthorType.USER
        )
        cls.note_type = NodeType.objects.create(name="Note", description="General note")
        cls.decision_type = NodeType.objects.create(
            name="Decision", description="Decision record"
        )
        cls.discusses_type = RelationshipType.objects.create(name="discusses")

    def setUp(self):
        self.live_node = Node.objects.create(
            title="Original Note",
            summary="This is the original summary",
            content="Original detailed content",
            node_type=self.note_type,
            author=self.author,
        )

    @async_to_sync()
    async def call_mcp_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call an MCP tool with flat arguments."""
        async with Client(mcp) as client:
            await client.ping()
            result = await client.call_tool(tool_name, arguments)
            # FastMCP returns different structures depending on version
            return result.data if hasattr(result, "data") else result

    @async_to_sync()
    async def get_mcp_resource(self, resource_name: str) -> list[dict]:
        """Read an MCP resource."""
        async with Client(mcp) as client:
            await client.ping()
            results = await client.read_resource(resource_name)
            return [r.model_dump() for r in results]
