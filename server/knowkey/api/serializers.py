from knowkey.core.models import (
    Author,
    Node,
    NodeRelationship,
    NodeType,
    RelationshipType,
    Tag,
)
from rest_framework import serializers


class AuthorSerializer(serializers.ModelSerializer):
    author_type_display = serializers.CharField(
        source="get_author_type_display", read_only=True
    )

    class Meta:
        model = Author
        fields = ["id", "name", "author_type", "author_type_display", "created_at"]


class NodeTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = NodeType
        fields = ["id", "name", "description", "icon", "color"]


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name", "description", "color", "created_at"]


class NodeSerializer(serializers.ModelSerializer):
    """Full serializer used for detail, create, update, and revert responses"""

    node_type = NodeTypeSerializer(read_only=True)
    node_type_id = serializers.UUIDField(write_only=True, required=True)

    author = AuthorSerializer(read_only=True)
    author_id = serializers.UUIDField(write_only=True, required=True)

    tags = TagSerializer(many=True, read_only=True)
    tags_ids = serializers.ListField(
        child=serializers.UUIDField(), write_only=True, required=False
    )

    is_latest = serializers.BooleanField(read_only=True)
    embedding = serializers.ListField(read_only=True, child=serializers.FloatField())

    class Meta:
        model = Node
        fields = [
            "id",
            "title",
            "summary",
            "content",
            "embedding",
            "node_type",
            "node_type_id",
            "author",
            "author_id",
            "version_of",
            "version_number",
            "is_latest",
            "metadata",
            "is_archived",
            "created_at",
            "updated_at",
            "tags",
            "tags_ids",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "version_number",
            "is_latest",
        ]

    def create(self, validated_data):
        tags_ids = validated_data.pop("tags_ids", [])
        node_type_id = validated_data.pop("node_type_id")
        author_id = validated_data.pop("author_id")

        node = Node.objects.create(
            node_type_id=node_type_id,
            author_id=author_id,
            **validated_data,
        )

        if tags_ids:
            node.tags.set(tags_ids)

        return node

    def update(self, instance, validated_data):
        tags_ids = validated_data.pop("tags_ids", None)
        node_type_id = validated_data.pop("node_type_id", None)
        author_id = validated_data.pop("author_id", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if node_type_id is not None:
            instance.node_type_id = node_type_id
        if author_id is not None:
            instance.author_id = author_id

        instance.save()

        if tags_ids is not None:
            instance.tags.set(tags_ids)

        return instance


class NodeListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views (fast)"""

    node_type = NodeTypeSerializer(read_only=True)
    author = AuthorSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    is_latest = serializers.BooleanField(read_only=True)

    class Meta:
        model = Node
        fields = [
            "id",
            "title",
            "summary",
            "node_type",
            "author",
            "tags",
            "version_number",
            "is_latest",
            "is_archived",
            "created_at",
            "updated_at",
        ]


class NodeRelationshipSerializer(serializers.ModelSerializer):
    relationship_type_display = serializers.CharField(
        source="get_relationship_type_display", read_only=True
    )

    class Meta:
        model = NodeRelationship
        fields = [
            "id",
            "source",
            "target",
            "relationship_type",
            "relationship_type_display",
            "weight",
            "created_by",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate(self, data):
        """Enforce the model's rule: relationships only between live nodes."""
        # Build a temporary instance so we can run model validation
        instance = NodeRelationship(
            source=data.get("source"),
            target=data.get("target"),
            relationship_type=data.get("relationship_type"),
            weight=data.get("weight", 1.0),
            created_by=data.get("created_by"),
        )
        instance.full_clean()  # This calls NodeRelationship.clean()
        return data
