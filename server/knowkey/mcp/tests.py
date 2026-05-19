"""
Tests for the Knowkey MCP Server.

Combines:
- Django model tests
- FastMCP Client-based tests (recommended pattern from gofastmcp.com)

Run with:
    python -m pytest knowkey/mcp/tests.py -v
    or
    python manage.py test knowkey.mcp
"""

import asyncio
from typing import Any

import pytest
from django.test import TestCase
from fastmcp import Client

from knowkey.core.models import Author, AuthorType, Node, NodeType, Tag
from knowkey.mcp.server import mcp
from knowkey.mcp.utils import async_to_sync


# =============================================================================
# Django + FastMCP Hybrid Test Base
# =============================================================================
class MCPTestCase(TestCase):
    """Base class that sets up Django data + provides async MCP client helper."""

    @classmethod
    def setUpTestData(cls):
        cls.author = Author.objects.create(name="Test User", author_type=AuthorType.USER)
        cls.note_type = NodeType.objects.create(name="Note", description="General note")
        cls.decision_type = NodeType.objects.create(name="Decision", description="Decision")

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
        """Helper to call MCP tools using the in-memory FastMCP client."""
        async with Client(mcp) as client:
            await client.ping()
            result = await client.call_tool(tool_name, arguments)
            return result.data if hasattr(result, "data") else result

    @async_to_sync()
    async def get_mcp_resource(self, resource_name: str) -> Any:
        """Helper to get MCP resources using the in-memory FastMCP client."""
        async with Client(mcp) as client:
            await client.ping()
            results = await client.read_resource(resource_name)
            data = []
            for result in results:
                data.append(result.model_dump_json())
            return data


# =============================================================================
# Django Model Tests (existing style)
# =============================================================================
class KnowkeyMCPModelTests(MCPTestCase):
    def test_create_node_via_mcp_logic(self):
        from knowkey.mcp.core import create_knowkey_node

        node = create_knowkey_node(
            title="MCP Created Node",
            summary="Created through core helper",
            content="Full content",
            node_type_name="Note",
            tag_names=["test", "mcp"],
            author_name="Grok",
        )

        self.assertTrue(node.is_latest)
        self.assertEqual(node.metadata.get("source"), "mcp")
        self.assertEqual(node.tags.count(), 2)

    def test_revert_functionality_exists(self):
        # Ensure the model method is available
        self.assertTrue(hasattr(self.live_node, "revert_to"))


# =============================================================================
# FastMCP Client Tests (Recommended Pattern)
# =============================================================================
class MCPToolsTests(MCPTestCase):
    def test_search_nodes_tool_exists(self):
        """Basic smoke test that the tool is registered."""
        tools = asyncio.run(self._list_tools())
        tool_names = [t.name for t in tools]
        self.assertIn("search_nodes", tool_names)

    async def _list_tools(self):
        async with Client(mcp) as client:
            return await client.list_tools()

    def test_search_nodes_returns_live_nodes(self):
        # Create a second version
        self.live_node.title = "Updated Title"
        self.live_node.save()

        result = self.call_mcp_tool(
            "search_nodes",
            {
                "params": {
                    "query": "Updated",
                    "include_all_versions": False,
                }
            },
        )

        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["is_latest"])

    def test_create_node_tool(self):
        result = self.call_mcp_tool(
            "create_node",
            {
                "params": {
                    "title": "MCP Test Node",
                    "summary": "This node was created by the MCP test suite",
                    "content": "Detailed test content here.",
                    "node_type_name": "Note",
                    "tag_names": ["test"],
                }
            },
        )

        self.assertTrue(result.get("success"))
        self.assertIn("id", result)

        # Verify it exists and has MCP metadata
        node = Node.objects.get(id=result["id"])
        self.assertEqual(node.metadata.get("source"), "mcp")

    def test_create_relationship_only_between_live_nodes(self):
        other = Node.objects.create(
            title="Other Live Node",
            node_type=self.note_type,
            author=self.author,
        )

        # This should succeed
        result = self.call_mcp_tool(
            "create_relationship",
            {
                "params": {
                    "source_node_id": str(self.live_node.id),
                    "target_node_id": str(other.id),
                    "relationship_type": "discusses",
                }
            },
        )
        self.assertTrue(result.get("success"))

        # Create a snapshot and try to link to it (should fail)
        snapshot = self.live_node.create_manual_snapshot()

        with self.assertRaises(Exception):  # ToolError wrapped
            self.call_mcp_tool(
                "create_relationship",
                {
                    "params": {
                        "source_node_id": str(snapshot.id),  # not live
                        "target_node_id": str(other.id),
                        "relationship_type": "discusses",
                    }
                },
            )

    def test_revert_node_tool(self):
        # Make a change
        self.live_node.title = "Bad Change"
        self.live_node.save()
        bad_snapshot = self.live_node.versions.latest("version_number")

        # Get original snapshot
        original_snapshot = self.live_node.versions.get(version_number=1)

        result = self.call_mcp_tool(
            "revert_node",
            {
                "params": {
                    "node_id": str(self.live_node.id),
                    "snapshot_id": str(original_snapshot.id),
                }
            },
        )

        self.assertTrue(result.get("success"))
        self.live_node.refresh_from_db()
        self.assertEqual(self.live_node.title, "Original Note")
        self.assertEqual(self.live_node.version_number, 3)  # bad state + revert


# =============================================================================
# Resource Tests (via Client)
# =============================================================================
class MCPResourcesTests(MCPTestCase):
    def test_ontology_resources(self):
        node_types = self.get_mcp_resource("knowkey://ontology/node_types")
        rel_types = self.get_mcp_resource("knowkey://ontology/relationship_types")

        self.assertIn("discusses", str(rel_types))
        self.assertIn("Note", str(node_types))
