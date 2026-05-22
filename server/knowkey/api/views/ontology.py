from rest_framework import viewsets

from knowkey.api.serializers import (
    NodeTypeSerializer,
    RelationshipTypeSerializer,
    TagSerializer,
)
from knowkey.core.models import NodeType, RelationshipType, Tag


class NodeTypeViewSet(viewsets.ModelViewSet):
    queryset = NodeType.objects.all()
    serializer_class = NodeTypeSerializer


class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer


class RelationshipTypeViewSet(viewsets.ModelViewSet):
    queryset = RelationshipType.objects.all()
    serializer_class = RelationshipTypeSerializer
