from django.test import TestCase

from knowkey.core.models import Author, AuthorType, Node, NodeType, Tag


class OntologyTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.author = Author.objects.create(name="Grok", author_type=AuthorType.CHATBOT)
        cls.person_type = NodeType.objects.create(name="Person")

    def test_tag_management(self):
        node = Node.objects.create(
            title="Test Node", node_type=self.person_type, author=self.author
        )
        tag1 = Tag.objects.create(name="alpha-ape")
        tag2 = Tag.objects.create(name="founder")

        node.tags.add(tag1, tag2)
        self.assertEqual(node.tags.count(), 2)
