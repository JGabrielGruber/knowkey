from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Author, Node, NodeRelationship, NodeType, Tag
from .serializers import (
    AuthorSerializer,
    NodeListSerializer,
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
    queryset = Node.objects.with_related()
    serializer_class = NodeSerializer  # default (detail)

    def get_queryset(self):
        qs = Node.objects.with_related()  # always use our smart manager

        # Default: only latest versions (what 🦍 and 🐒 want)
        if self.action == "list":
            include_all = (
                self.request.query_params.get("include_all_versions", "false").lower()
                == "true"
            )
            if not include_all:
                qs = Node.objects.latest_versions()

            # Layer 0/1 — shallow fields only
            qs = qs.only(
                "id",
                "title",
                "summary",
                "node_type_id",
                "author_id",
                "version_number",
                "is_archived",
                "created_at",
                "updated_at",
            )

            return qs

        # For detail, create, update → full object
        return qs

    # Use different serializer for list
    def get_serializer_class(self):
        if self.action == "list":
            return NodeListSerializer
        return NodeSerializer

    # Keep your filters (they still work perfectly)
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["node_type__name", "author__id", "is_archived", "tags__name"]
    search_fields = ["title", "summary"]
    ordering_fields = ["created_at", "updated_at", "title"]


class NodeRelationshipViewSet(viewsets.ModelViewSet):
    queryset = NodeRelationship.objects.all().select_related(
        "source", "target", "created_by"
    )
    serializer_class = NodeRelationshipSerializer
