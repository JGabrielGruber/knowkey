from django.test import TestCase

from knowkey.core.models import Author, AuthorType


class AuthorTests(TestCase):

    def test_author_creation(self):
        author = Author.objects.create(
            name="José Gabriel Gruber", author_type=AuthorType.USER
        )
        self.assertEqual(author.name, "José Gabriel Gruber")
