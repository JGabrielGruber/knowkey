from .base import MCPTestCase


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
