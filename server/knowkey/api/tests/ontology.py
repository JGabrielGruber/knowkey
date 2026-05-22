from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class TagAndTypeAPITests(APITestCase):

    def test_list_node_types(self):
        url = reverse("nodetype-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
