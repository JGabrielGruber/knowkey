"""
Tests for the Knowkey MCP Server.

Combines Django model tests + FastMCP Client tests.
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
# Test Base Class
# =============================================================================
class MCPTestCase(TestCase):
    """Base class with common setup and MCP helpers."""

    @classmethod
    def setUpTestData(cls):
        cls.author = Author.objects.create(
            name="Test User", author_type=AuthorType.USER
        )
        cls.note_type = NodeType.objects.create(
            name="Note", description="General note"
        )
        cls.decision_type = NodeType.objects.create(
            name="Decision", description="Decision record"
        )

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


# =============================================================================
# Model / Core Logic Tests
# =============================================================================
class KnowkeyMCPModelTests(MCPTestCase):

    def test_create_knowkey_node_helper(self):
        from knowkey.mcp.core import create_knowkey_node

        node = create_knowkey_node(
            title="MCP Created Node",
            summary="Created through core helper",
            content="Full content here",
            node_type_name="Note",
            tag_names=["test", "mcp"],
            author_name="Grok",
        )

        self.assertTrue(node.is_latest)
        self.assertEqual(node.metadata.get("source"), "mcp")
        self.assertEqual(node.tags.count(), 2)
        self.assertEqual(node.version_number, 1)

    def test_revert_functionality_exists(self):
        self.assertTrue(hasattr(self.live_node, "revert_to"))


# =============================================================================
# Tool Tests
# =============================================================================
class MCPToolsTests(MCPTestCase):

    def test_search_nodes_tool_exists(self):
        tools = asyncio.run(self._list_tools())
        tool_names = [t.name for t in tools]
        self.assertIn("search_nodes", tool_names)
        self.assertIn("create_node", tool_names)

    async def _list_tools(self):
        async with Client(mcp) as client:
            return await client.list_tools()

    def test_search_nodes_returns_only_live_nodes_by_default(self):
        # Create a new version
        self.live_node.title = "Updated Title"
        self.live_node.save()

        result = self.call_mcp_tool(
            "search_nodes",
            {
                "query": "Updated",
                "include_all_versions": False,
            },
        )

        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["is_latest"])
        self.assertEqual(result[0]["title"], "Updated Title")

    def test_create_node_tool(self):
        result = self.call_mcp_tool(
            "create_node",
            {
                "title": "MCP Test Node",
                "summary": "This node was created by the MCP test suite",
                "content": "Detailed test content here.",
                "node_type_name": "Note",
                "tag_names": ["test", "automation"],
            },
        )

        self.assertTrue(result.get("success"))
        self.assertIn("id", result)

        # Verify in database
        node = Node.objects.get(id=result["id"])
        self.assertEqual(node.title, "MCP Test Node")
        self.assertEqual(node.metadata.get("source"), "mcp")
        self.assertEqual(node.tags.count(), 2)

    def test_update_node_tool(self):
        result = self.call_mcp_tool(
            "update_node",
            {
                "node_id": str(self.live_node.id),
                "title": "Updated via MCP Tool",
                "summary": "New improved summary",
            },
        )

        self.assertTrue(result.get("success"))
        self.live_node.refresh_from_db()
        self.assertEqual(self.live_node.title, "Updated via MCP Tool")
        self.assertEqual(self.live_node.version_number, 2)

    def test_create_relationship_only_between_live_nodes(self):
        other = Node.objects.create(
            title="Other Live Node",
            node_type=self.note_type,
            author=self.author,
        )

        result = self.call_mcp_tool(
            "create_relationship",
            {
                "source_node_id": str(self.live_node.id),
                "target_node_id": str(other.id),
                "relationship_type": "discusses",
            },
        )

        self.assertTrue(result.get("success"))

        # Try with snapshot → should fail
        snapshot = self.live_node.create_manual_snapshot()
        with self.assertRaises(Exception):  # ToolError
            self.call_mcp_tool(
                "create_relationship",
                {
                    "source_node_id": str(snapshot.id),
                    "target_node_id": str(other.id),
                    "relationship_type": "discusses",
                },
            )

    def test_revert_node_tool(self):
        # Make a bad change
        self.live_node.title = "Bad Change"
        self.live_node.save()
        bad_snapshot = self.live_node.versions.latest("version_number")

        # Revert to original
        original_snapshot = self.live_node.versions.get(version_number=1)

        result = self.call_mcp_tool(
            "revert_node",
            {
                "node_id": str(self.live_node.id),
                "snapshot_id": str(original_snapshot.id),
            },
        )

        self.assertTrue(result.get("success"))
        self.live_node.refresh_from_db()
        self.assertEqual(self.live_node.title, "Original Note")
        self.assertEqual(self.live_node.version_number, 3)  # bad + revert


# =============================================================================
# Resource Tests
# =============================================================================
class MCPResourcesTests(MCPTestCase):

    def test_ontology_resources(self):
        node_types = self.get_mcp_resource("knowkey://ontology/node_types")
        rel_types = self.get_mcp_resource("knowkey://ontology/relationship_types")

        self.assertGreater(len(node_types), 0)
        self.assertIn("Note", str(node_types))
        self.assertIn("discusses", str(rel_types))

    def test_node_resource(self):
        data = self.get_mcp_resource(f"knowkey://node/{self.live_node.id}")
        self.assertGreater(len(data), 0)
        self.assertIn("Original", str(data))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
