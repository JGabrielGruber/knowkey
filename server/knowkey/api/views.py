from django_filters.rest_framework import DjangoFilterBackend
from knowkey.core.models import Author, Node, NodeRelationship, NodeType, Tag
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

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
    serializer_class = NodeSerializer

    def get_queryset(self):
        qs = Node.objects.with_related()

        # Default behavior: only latest versions (what most clients want)
        if self.action in ["list", "retrieve"]:
            include_all = (
                self.request.query_params.get("include_all_versions", "false").lower()
                == "true"
            )
            if not include_all:
                qs = Node.objects.latest_versions()

        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return NodeListSerializer
        return NodeSerializer

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["node_type__name", "author__id", "is_archived", "tags__name"]
    search_fields = ["title", "summary"]
    ordering_fields = ["created_at", "updated_at", "title"]

    # ====================== NEW: REVERT ACTION ======================
    @action(detail=True, methods=["post"], url_path="revert")
    def revert(self, request, pk=None):
        """Revert this live node to a previous snapshot.
        Example payload: {"snapshot_id": "uuid-of-snapshot"}"""
        node = self.get_object()

        if not node.is_latest:
            return Response(
                {"error": "Can only revert the live (latest) version"}, status=400
            )

        snapshot_id = request.data.get("snapshot_id")
        if not snapshot_id:
            return Response({"error": "snapshot_id is required"}, status=400)

        try:
            snapshot = Node.objects.get(id=snapshot_id, version_of=node)
        except Node.DoesNotExist:
            return Response(
                {"error": "Snapshot not found or does not belong to this node"},
                status=404,
            )

        node.revert_to(snapshot, bypass_versioning=False)
        serializer = self.get_serializer(node)
        return Response(serializer.data)

    # ====================== NEW: HISTORY ENDPOINT ======================
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        """Return full version history of this node (newest first)"""
        node = self.get_object()
        history = node.get_full_history()

        serializer = NodeListSerializer(
            history, many=True, context=self.get_serializer_context()
        )
        return Response(serializer.data)


class NodeRelationshipViewSet(viewsets.ModelViewSet):
    queryset = NodeRelationship.objects.all().select_related(
        "source", "target", "created_by"
    )
    serializer_class = NodeRelationshipSerializer
