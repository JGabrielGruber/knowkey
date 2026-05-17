from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import Author, AuthorType, Node, NodeRelationship, NodeType


class KnowkeyCoreTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.author = Author.objects.create(
            name="Test User", author_type=AuthorType.USER
        )
        cls.node_type = NodeType.objects.create(name="Note")

    def setUp(self):
        # Fresh live node for each test
        self.live = Node.objects.create(
            title="Original Title",
            summary="Original summary",
            content="Original content",
            node_type=self.node_type,
            author=self.author,
        )

    # ====================== BASIC VERSIONING ======================
    def test_new_node_is_live_version_1(self):
        self.assertTrue(self.live.is_latest)
        self.assertEqual(self.live.version_number, 1)
        self.assertIsNone(self.live.version_of)

    def test_edit_creates_snapshot_and_increments_version(self):
        self.live.title = "New Title"
        self.live.content = "New content"
        self.live.save()

        self.live.refresh_from_db()
        self.assertEqual(self.live.version_number, 2)
        self.assertTrue(self.live.is_latest)

        # Check snapshot was created
        snapshot = self.live.versions.get(version_number=1)
        self.assertEqual(snapshot.title, "Original Title")
        self.assertEqual(snapshot.content, "Original content")
        self.assertFalse(snapshot.is_latest)

    def test_minor_changes_do_not_create_snapshot(self):
        self.live.metadata["foo"] = "bar"
        self.live.save()  # only metadata changed

        self.live.refresh_from_db()
        self.assertEqual(self.live.version_number, 1)  # no increment
        self.assertEqual(self.live.versions.count(), 0)

    # ====================== MANUAL SNAPSHOT ======================
    def test_create_manual_snapshot(self):
        snapshot = self.live.create_manual_snapshot()

        self.assertEqual(snapshot.version_number, 1)
        self.assertEqual(snapshot.version_of, self.live)
        self.assertEqual(self.live.versions.count(), 1)

    # ====================== REVERT MAGIC ======================
    def test_revert_to_snapshot_restores_content_and_relationships(self):
        # 1. Add a relationship
        rel = NodeRelationship.objects.create(
            source=self.live,
            target=self.live,  # self-relationship for simplicity
            relationship_type="discusses",
            created_by=self.author,
        )

        # 2. Edit the node (creates snapshot v2)
        self.live.title = "Changed Title"
        self.live.content = "Changed content"
        self.live.save()

        snapshot_v1 = self.live.versions.get(version_number=1)

        # 3. Revert
        self.live.revert_to(snapshot_v1, bypass_versioning=False)

        self.live.save()

        self.live.refresh_from_db()

        self.assertEqual(self.live.title, "Original Title")
        self.assertEqual(self.live.content, "Original content")
        self.assertEqual(self.live.version_number, 3)  # new history entry created

        # Relationship was restored
        self.assertEqual(self.live.outgoing_relationships.count(), 1)
        restored_rel = self.live.outgoing_relationships.first()
        self.assertEqual(restored_rel.relationship_type, "discusses")

        # History is preserved (we have v1 and v2 + live)
        self.assertEqual(self.live.versions.count(), 2)

    def test_revert_creates_history_of_bad_state_first(self):
        self.live.title = "Bad Change"
        self.live.save()
        snapshot_bad = self.live.versions.latest("version_number")

        original_snapshot = self.live.versions.get(version_number=1)

        self.live.revert_to(original_snapshot, bypass_versioning=False)

        # We should now have: original → bad → reverted (2 snapshots + live)
        self.assertEqual(self.live.versions.count(), 2)

    # ====================== RELATIONSHIP SAFETY ======================
    def test_relationships_only_allowed_between_live_nodes(self):
        snapshot = self.live.create_manual_snapshot()

        with self.assertRaises(ValidationError):
            rel = NodeRelationship(
                source=snapshot,  # not live
                target=self.live,
                relationship_type="discusses",
                created_by=self.author,
            )
            rel.full_clean()

    # ====================== MANAGERS ======================
    def test_latest_versions_manager(self):
        self.live.title = "Edited"
        self.live.save()

        all_nodes = Node.objects.all_versions().count()
        live_only = Node.objects.latest_versions().count()

        self.assertEqual(live_only, 1)
        self.assertEqual(all_nodes, 2)  # live + snapshot

    def test_get_full_history(self):
        self.live.title = "v2"
        self.live.save()
        self.live.title = "v3"
        self.live.save()

        history = self.live.get_full_history()
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0].version_number, 3)
        self.assertEqual([n.version_number for n in history], [3, 2, 1])

    # ====================== SOFT DELETE ======================
    def test_delete_archives_instead_of_hard_deleting(self):
        self.live.delete()
        self.live.refresh_from_db()
        self.assertTrue(self.live.is_archived)

    # ====================== EDGE CASES ======================
    def test_cannot_revert_snapshot_itself(self):
        snapshot = self.live.create_manual_snapshot()
        with self.assertRaises(ValueError):
            snapshot.revert_to(snapshot)  # wrong

    def test_cannot_revert_with_wrong_snapshot(self):
        other_node = Node.objects.create(
            title="Other", node_type=self.node_type, author=self.author
        )
        snapshot = other_node.create_manual_snapshot()
        with self.assertRaises(ValueError):
            self.live.revert_to(snapshot)
