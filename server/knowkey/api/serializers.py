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


class RelationshipTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RelationshipType
        fields = ["id", "name", "description", "icon", "color"]


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name", "description", "color", "created_at"]


class NodeSerializer(serializers.ModelSerializer):
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


class NodeListSerializer(serializers.ModelSerializer):
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
    relationship_type = RelationshipTypeSerializer(read_only=True)
    relationship_type_id = serializers.UUIDField(write_only=True, required=True)
    source_id = serializers.UUIDField(
        write_only=True, required=True
    )  # renamed for clarity
    target_id = serializers.UUIDField(write_only=True, required=True)
    created_by_id = serializers.UUIDField(write_only=True, required=True)

    class Meta:
        model = NodeRelationship
        fields = [
            "id",
            "source_id",  # Changed from 'source'
            "target_id",  # Changed from 'target'
            "relationship_type",
            "relationship_type_id",
            "weight",
            "created_by_id",  # Changed from 'created_by'
            "created_at",
        ]
        read_only_fields = ["id", "created_at", "relationship_type"]

    def create(self, validated_data):
        relationship_type_id = validated_data.pop("relationship_type_id")
        source_id = validated_data.pop("source_id")
        target_id = validated_data.pop("target_id")
        created_by_id = validated_data.pop("created_by_id")

        relationship_type = RelationshipType.objects.get(id=relationship_type_id)
        source = Node.objects.get(id=source_id)
        target = Node.objects.get(id=target_id)
        created_by = Author.objects.get(id=created_by_id)

        return NodeRelationship.objects.create(
            source=source,
            target=target,
            relationship_type=relationship_type,
            created_by=created_by,
            **validated_data,
        )
