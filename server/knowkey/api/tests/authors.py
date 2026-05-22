from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from knowkey.core.models import Author, AuthorType


class AuthorAPITests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.author = Author.objects.create(
            name="Test User", author_type=AuthorType.USER
        )

    def test_list_authors(self):
        url = reverse("author-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Handle paginated or non-paginated response
        if isinstance(response.data, dict) and "results" in response.data:
            results = response.data["results"]
        else:
            results = response.data
        names = [item["name"] for item in results]
        self.assertIn("Test User", names)
