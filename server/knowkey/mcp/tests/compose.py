from .base import MCPTestCase


class KnowkeyMCPModelTests(MCPTestCase):

    def test_create_knowkey_node_helper(self):
        from knowkey.mcp.core import create_node

        node = create_node(
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
