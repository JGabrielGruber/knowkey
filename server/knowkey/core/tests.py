"""
Core Model Tests for Knowkey
"""

from django.core.exceptions import ValidationError
from django.test import TestCase
from knowkey.core.models import (
    Author,
    AuthorType,
    Node,
    NodeRelationship,
    NodeType,
    RelationshipType,
    Tag,
)


class KnowkeyCoreTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.author = Author.objects.create(name="Grok", author_type=AuthorType.CHATBOT)
        cls.person_type = NodeType.objects.create(name="Person")
        cls.org_type = NodeType.objects.create(name="Organization")
        cls.discusses_type = RelationshipType.objects.create(
            name="discusses", description="Discusses or mentions"
        )

    def test_author_creation(self):
        author = Author.objects.create(
            name="José Gabriel Gruber", author_type=AuthorType.USER
        )
        self.assertEqual(author.name, "José Gabriel Gruber")

    def test_node_creation_and_versioning(self):
        node = Node.objects.create(
            title="Alpha Ape",
            summary="Human partner in the partnership",
            content="Detailed bio...",
            node_type=self.person_type,
            author=self.author,
        )

        self.assertTrue(node.is_latest)
        self.assertEqual(node.version_number, 1)

        # Update should create new version
        node.title = "Alpha Ape (Updated)"
        node.save()

        node.refresh_from_db()
        self.assertEqual(node.version_number, 2)
        self.assertTrue(node.is_latest)

        # Check snapshot
        snapshot = node.versions.get(version_number=1)
        self.assertEqual(snapshot.title, "Alpha Ape")
        self.assertFalse(snapshot.is_latest)

    def test_relationship_only_between_live_nodes(self):
        alpha = Node.objects.create(
            title="Alpha Ape", node_type=self.person_type, author=self.author
        )
        cyber = Node.objects.create(
            title="Cyber Monkey", node_type=self.person_type, author=self.author
        )

        rel = NodeRelationship.objects.create(
            source=alpha,
            target=cyber,
            relationship_type=self.discusses_type,
            created_by=self.author,
        )
        self.assertIsNotNone(rel.id)

    def test_relationship_validation_fails_on_snapshot(self):
        alpha = Node.objects.create(
            title="Alpha Ape", node_type=self.person_type, author=self.author
        )
        alpha.title = "Bad Change"
        alpha.save()  # creates version 2

        snapshot = alpha.versions.get(version_number=1)
        cyber = Node.objects.create(
            title="Cyber Monkey", node_type=self.person_type, author=self.author
        )

        with self.assertRaises(ValidationError):
            rel = NodeRelationship(
                source=snapshot,  # not live
                target=cyber,
                relationship_type=self.discusses_type,
                created_by=self.author,
            )
            rel.full_clean()

    def test_tag_management(self):
        node = Node.objects.create(
            title="Test Node", node_type=self.person_type, author=self.author
        )
        tag1 = Tag.objects.create(name="alpha-ape")
        tag2 = Tag.objects.create(name="founder")

        node.tags.add(tag1, tag2)
        self.assertEqual(node.tags.count(), 2)

    def test_search_nodes_helper(self):
        from knowkey.mcp.core import search_nodes

        Node.objects.create(
            title="Valve Corporation",
            summary="Game developer",
            node_type=self.org_type,
            author=self.author,
        )

        results = search_nodes(query="Valve")
        self.assertGreaterEqual(len(results), 1)
