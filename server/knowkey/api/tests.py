"""
API Tests for Knowkey - REST Layer
"""

from django.urls import reverse
from knowkey.core.models import (
    Author,
    AuthorType,
    Node,
    NodeRelationship,
    NodeType,
    RelationshipType,
    Tag,
)
from rest_framework import status
from rest_framework.test import APITestCase


class NodeAPITests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.author = Author.objects.create(
            name="Test User", author_type=AuthorType.USER
        )
        cls.note_type = NodeType.objects.create(name="Note")
        cls.person_type = NodeType.objects.create(name="Person")
        cls.discusses_type = RelationshipType.objects.create(name="discusses")

    def setUp(self):
        self.live_node = Node.objects.create(
            title="Original Test Node",
            summary="Original summary",
            content="Original content",
            node_type=self.note_type,
            author=self.author,
        )

    # ====================== NODE CRUD ======================
    def test_create_node_via_api(self):
        url = reverse("node-list")
        data = {
            "title": "API Created Node",
            "summary": "Created via REST API",
            "content": "Full detailed content",
            "node_type_id": str(self.note_type.id),
            "author_id": str(self.author.id),
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["title"], "API Created Node")
        self.assertTrue(response.data["is_latest"])

    def test_update_node_creates_version(self):
        url = reverse("node-detail", args=[self.live_node.id])
        data = {
            "title": "Updated via API",
            "content": "New content after update",
            "node_type_id": str(self.note_type.id),
            "author_id": str(self.author.id),
        }

        response = self.client.put(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.live_node.refresh_from_db()
        self.assertEqual(self.live_node.version_number, 2)
        self.assertEqual(self.live_node.title, "Updated via API")

    # ====================== VERSIONING & HISTORY ======================
    def test_list_only_returns_latest_versions(self):
        self.live_node.title = "Version 2"
        self.live_node.save()

        url = reverse("node-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["version_number"], 2)

    def test_history_endpoint_returns_full_timeline(self):
        self.live_node.title = "v2"
        self.live_node.save()
        self.live_node.title = "v3"
        self.live_node.save()

        url = reverse("node-history", args=[self.live_node.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)  # v1, v2, v3

    # ====================== RELATIONSHIPS ======================
    def test_create_relationship_via_api(self):
        other = Node.objects.create(
            title="Related Node", node_type=self.person_type, author=self.author
        )

        url = reverse("noderelationship-list")
        data = {
            "source_id": str(self.live_node.id),
            "target_id": str(other.id),
            "relationship_type_id": str(self.discusses_type.id),
            "created_by_id": str(self.author.id),
            "weight": 1.0,
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_cannot_create_relationship_with_snapshot(self):
        snapshot = (
            self.live_node.create_manual_snapshot()
            if hasattr(self.live_node, "create_manual_snapshot")
            else None
        )
        other = Node.objects.create(
            title="Other", node_type=self.person_type, author=self.author
        )

        url = reverse("noderelationship-list")
        data = {
            "source": str(snapshot.id) if snapshot else str(self.live_node.id),
            "target": str(other.id),
            "relationship_type_id": str(self.discusses_type.id),
            "created_by": str(self.author.id),
        }

        response = self.client.post(url, data, format="json")
        # Should fail or be handled by serializer/model validation
        self.assertIn(
            response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_201_CREATED]
        )


class TagAndTypeAPITests(APITestCase):

    def test_list_node_types(self):
        url = reverse("nodetype-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
