"""
Tests for the Knowkey MCP Server.

These tests verify that the MCP tools and resources work correctly
with the Knowkey data models (versioning, live nodes, relationships, etc.).
"""

from django.test import TestCase
from knowkey.core.models import (
    Author,
    AuthorType,
    Node,
    NodeRelationship,
    NodeType,
    Tag,
)
from knowkey.mcp.server import create_node, create_relationship, get_node, search_nodes


class MCPToolsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = Author.objects.create(
            name="Test User", author_type=AuthorType.USER
        )
        cls.node_type = NodeType.objects.create(name="Note", description="General note")
        cls.decision_type = NodeType.objects.create(
            name="Decision", description="Important decision"
        )

    def setUp(self):
        # Create a live node for testing
        self.live_node = Node.objects.create(
            title="Original Note",
            summary="This is a test note",
            content="Detailed content here",
            node_type=self.node_type,
            author=self.author,
        )

    # ====================== CREATE NODE ======================
    def test_create_node_success(self):
        result = create_node(
            title="New Insight from MCP",
            summary="This was created via MCP server",
            content="Full content of the insight...",
            node_type_name="Note",
            tag_names=["mcp", "test"],
            author_name="Grok",
        )

        self.assertTrue(result.get("success"))
        self.assertIn("id", result)
        self.assertEqual(result["version_number"], 1)

        # Verify it exists in DB
        node = Node.objects.get(id=result["id"])
        self.assertEqual(node.title, "New Insight from MCP")
        self.assertEqual(node.tags.count(), 2)
        self.assertTrue(node.is_latest)

    def test_create_node_invalid_type(self):
        result = create_node(
            title="Bad Type",
            summary="Should fail",
            content="...",
            node_type_name="NonExistentType",
        )
        self.assertIn("error", result)

    # ====================== CREATE RELATIONSHIP ======================
    def test_create_relationship_between_live_nodes(self):
        other_node = Node.objects.create(
            title="Related Node",
            node_type=self.node_type,
            author=self.author,
        )

        result = create_relationship(
            source_node_id=str(self.live_node.id),
            target_node_id=str(other_node.id),
            relationship_type="discusses",
        )

        self.assertTrue(result.get("success"))
        self.assertEqual(NodeRelationship.objects.count(), 1)

    def test_create_relationship_fails_on_snapshot(self):
        # Create a snapshot manually
        snapshot = self.live_node.create_manual_snapshot()

        other = Node.objects.create(
            title="Other",
            node_type=self.node_type,
            author=self.author,
        )

        result = create_relationship(
            source_node_id=str(snapshot.id),  # snapshot, not live
            target_node_id=str(other.id),
            relationship_type="discusses",
        )

        self.assertIn("error", result)
        self.assertIn("live", result["error"].lower())

    # ====================== SEARCH NODES ======================
    def test_search_nodes_returns_only_live_by_default(self):
        # Create a second version
        self.live_node.title = "Updated Title"
        self.live_node.save()

        results = search_nodes(query="Updated")
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["is_latest"])

    def test_search_nodes_can_include_all_versions(self):
        self.live_node.title = "Version 2 Note"
        self.live_node.save()

        results = search_nodes(query="Note", include_all_versions=True)
        self.assertEqual(len(results), 2)

    def test_search_nodes_by_node_type(self):
        results = search_nodes(query="", node_type_name="Note")
        self.assertGreaterEqual(len(results), 1)

    # ====================== GET NODE ======================
    def test_get_node_returns_full_data(self):
        result = get_node(str(self.live_node.id))
        self.assertEqual(result["title"], "Original Note")
        self.assertIn("outgoing_relationships", result)
        self.assertIn("incoming_relationships", result)

    def test_get_node_not_found(self):
        result = get_node("00000000-0000-0000-0000-000000000000")
        self.assertIn("error", result)


class MCPRelationshipValidationTests(TestCase):
    """Specific tests for relationship safety rules."""

    def setUp(self):
        self.author = Author.objects.create(name="Test", author_type=AuthorType.USER)
        self.nt = NodeType.objects.create(name="TestType")

        self.node_a = Node.objects.create(
            title="A", node_type=self.nt, author=self.author
        )
        self.node_b = Node.objects.create(
            title="B", node_type=self.nt, author=self.author
        )

    def test_cannot_create_relationship_with_non_live_source(self):
        snapshot = self.node_a.create_manual_snapshot()

        result = create_relationship(
            source_node_id=str(snapshot.id),
            target_node_id=str(self.node_b.id),
            relationship_type="discusses",
        )
        self.assertIn("error", result)
