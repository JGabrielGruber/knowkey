from rest_framework import viewsets

from knowkey.api.serializers import AuthorSerializer
from knowkey.core.models import Author


class AuthorViewSet(viewsets.ModelViewSet):
    queryset = Author.objects.all()
    serializer_class = AuthorSerializer
