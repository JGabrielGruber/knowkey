import asyncio

from fastmcp import Client
from knowkey.core.models import Node, NodeType
from knowkey.mcp.server import mcp

from .base import MCPTestCase


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
                "relationship_type_name": "discusses",
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

    def test_create_node_type_tool(self):
        result = self.call_mcp_tool(
            "create_node_type",
            {
                "name": "Analysis",
                "description": "A recorded analysis with context, alternatives, and outcome",
                "icon": "⚖️",
                "color": "#10b981",
            },
        )

        self.assertTrue(result.get("success"))
        self.assertIn("id", result)
        self.assertEqual(result["name"], "Analysis")

        # Verify in DB
        nt = NodeType.objects.get(name="Analysis")
        self.assertEqual(
            nt.description,
            "A recorded analysis with context, alternatives, and outcome",
        )
        self.assertEqual(nt.icon, "⚖️")
        self.assertEqual(nt.color, "#10b981")

    def test_create_node_type_idempotent(self):
        # First creation
        self.call_mcp_tool(
            "create_node_type",
            {"name": "Concept", "description": "Abstract idea"},
        )

        # Second call should not duplicate
        result2 = self.call_mcp_tool(
            "create_node_type",
            {"name": "Concept", "description": "Updated description"},
        )

        self.assertFalse(result2.get("created"))  # already existed
        self.assertEqual(result2["name"], "Concept")

    def test_create_node_type_appears_in_ontology_resource(self):
        self.call_mcp_tool(
            "create_node_type",
            {"name": "Experiment", "icon": "🧪"},
        )

        ontology = self.get_mcp_resource("knowkey://ontology/node_types")
        self.assertIn("Experiment", str(ontology))

    def test_get_node_tool(self):
        """Test basic get_node functionality."""
        result = self.call_mcp_tool(
            "get_node",
            {"node_id": str(self.live_node.id)},
        )

        self.assertIn("id", result)
        self.assertIn("title", result)
        self.assertIn("summary", result)
        self.assertIn("node_type", result)
        self.assertEqual(result["title"], "Original Note")
        self.assertEqual(result["is_latest"], True)

    def test_get_node_with_relationships(self):
        """Test get_node includes relationships when they exist."""
        # Create a related node and relationship
        other = Node.objects.create(
            title="Related Knowledge",
            summary="This is related content",
            node_type=self.note_type,
            author=self.author,
        )

        # Create relationship
        self.call_mcp_tool(
            "create_relationship",
            {
                "source_node_id": str(self.live_node.id),
                "target_node_id": str(other.id),
                "relationship_type_name": "discusses",
            },
        )

        # Get the node with relationships
        result = self.call_mcp_tool(
            "get_node",
            {"node_id": str(self.live_node.id)},
        )

        self.assertIn("outgoing_relationships", result)
        self.assertGreaterEqual(len(result["outgoing_relationships"]), 1)

        rel = result["outgoing_relationships"][0]
        self.assertEqual(rel["relationship_type"], "discusses")
        self.assertEqual(rel["target_title"], "Related Knowledge")

    def test_get_node_nonexistent_raises_error(self):
        """Test that getting a non-existent node raises ToolError."""
        with self.assertRaises(Exception):  # Should be ToolError
            self.call_mcp_tool(
                "get_node",
                {"node_id": "00000000-0000-0000-0000-000000000000"},
            )
