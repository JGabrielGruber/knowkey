from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Author, Node, NodeRelationship, NodeType, Tag
from .serializers import (
    AuthorSerializer,
    NodeRelationshipSerializer,
    NodeSerializer,
    NodeTypeSerializer,
    TagSerializer,
)


class AuthorViewSet(viewsets.ModelViewSet):
    queryset = Author.objects.all()
    serializer_class = AuthorSerializer


class NodeTypeViewSet(viewsets.ModelViewSet):
    queryset = NodeType.objects.all()
    serializer_class = NodeTypeSerializer


class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer


class NodeViewSet(viewsets.ModelViewSet):
    queryset = Node.objects.all().select_related("node_type", "author")
    serializer_class = NodeSerializer

    # Example custom action later for search
    @action(detail=False, methods=["get"])
    def search(self, request):
        # placeholder — we'll make this powerful soon
        return Response({"message": "Semantic search coming soon with pgvector!"})


class NodeRelationshipViewSet(viewsets.ModelViewSet):
    queryset = NodeRelationship.objects.all().select_related(
        "source", "target", "created_by"
    )
    serializer_class = NodeRelationshipSerializer
