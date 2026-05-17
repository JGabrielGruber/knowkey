from django.urls import reverse
from knowkey.core.models import (
    Author,
    AuthorType,
    Node,
    NodeRelationship,
    NodeType,
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
        cls.node_type = NodeType.objects.create(name="Note")

    def setUp(self):
        self.client = self.client_class()  # APITestCase client
        self.live_node = Node.objects.create(
            title="Original Title",
            summary="Original summary",
            content="Original content",
            node_type=self.node_type,
            author=self.author,
        )

    # ====================== BASIC CRUD ======================
    def test_create_node_via_api(self):
        url = reverse("node-list")
        data = {
            "title": "API Created Node",
            "summary": "Created via API",
            "content": "Full content here",
            "node_type_id": str(self.node_type.id),
            "author_id": str(self.author.id),
            "tags_ids": [],
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["title"], "API Created Node")
        self.assertTrue(response.data["is_latest"])

    def test_update_node_creates_version(self):
        url = reverse("node-detail", args=[self.live_node.id])
        data = {
            "title": "Updated via API",
            "content": "New content",
            "node_type_id": str(self.node_type.id),
            "author_id": str(self.author.id),
        }

        response = self.client.put(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.live_node.refresh_from_db()
        self.assertEqual(self.live_node.version_number, 2)
        self.assertEqual(self.live_node.title, "Updated via API")

        # Snapshot should exist
        self.assertEqual(self.live_node.versions.count(), 1)

    # ====================== LIST & VERSIONING ======================
    def test_list_only_returns_latest_versions_by_default(self):
        # Create a second version
        self.live_node.title = "Version 2"
        self.live_node.save()

        url = reverse("node-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)  # only the live head
        self.assertEqual(response.data["results"][0]["version_number"], 2)

    def test_list_can_include_all_versions(self):
        self.live_node.title = "Version 2"
        self.live_node.save()

        url = reverse("node-list") + "?include_all_versions=true"
        response = self.client.get(url)

        self.assertEqual(len(response.data["results"]), 2)

    # ====================== HISTORY ENDPOINT ======================
    def test_history_endpoint_returns_full_timeline(self):
        # Create two versions
        self.live_node.title = "v2"
        self.live_node.save()
        self.live_node.title = "v3"
        self.live_node.save()

        url = reverse("node-history", args=[self.live_node.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)  # v3, v2, v1 (live is v3)

    # ====================== REVERT ENDPOINT ======================
    def test_revert_endpoint_works(self):
        # Create a snapshot
        self.live_node.title = "Bad Change"
        self.live_node.save()
        snapshot = self.live_node.versions.get(version_number=1)

        url = reverse("node-revert", args=[self.live_node.id])
        data = {"snapshot_id": str(snapshot.id)}

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Original Title")
        self.assertEqual(response.data["version_number"], 3)  # new history entry

    def test_revert_fails_on_non_live_node(self):
        snapshot = self.live_node.create_manual_snapshot()
        url = reverse("node-revert", args=[snapshot.id])  # trying to revert a snapshot
        data = {"snapshot_id": str(self.live_node.id)}

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ====================== RELATIONSHIPS ======================
    def test_create_relationship_between_live_nodes(self):
        other = Node.objects.create(
            title="Other Node", node_type=self.node_type, author=self.author
        )

        url = reverse("noderelationship-list")
        data = {
            "source": str(self.live_node.id),
            "target": str(other.id),
            "relationship_type": "discusses",
            "weight": 1.0,
            "created_by": str(self.author.id),
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_cannot_create_relationship_with_snapshot(self):
        snapshot = self.live_node.create_manual_snapshot()
        other = Node.objects.create(
            title="Other", node_type=self.node_type, author=self.author
        )

        url = reverse("noderelationship-list")
        data = {
            "source": str(snapshot.id),  # not live
            "target": str(other.id),
            "relationship_type": "discusses",
            "created_by": str(self.author.id),
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ====================== SERIALIZER EDGE CASES ======================
    def test_node_serializer_handles_tags_ids_correctly(self):
        tag = Tag.objects.create(name="test-tag")  # assuming you have Tag model

        url = reverse("node-list")
        data = {
            "title": "With Tags",
            "node_type_id": str(self.node_type.id),
            "author_id": str(self.author.id),
            "tags_ids": [str(tag.id)],
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data["tags"]), 1)
