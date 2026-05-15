from rest_framework import serializers

from .models import (
    Author,
    AuthorType,
    Node,
    NodeRelationship,
    NodeType,
    RelationshipType,
    Tag,
)


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
    node_type = NodeTypeSerializer(read_only=True)
    node_type_id = serializers.UUIDField(write_only=True, required=True)

    author = AuthorSerializer(read_only=True)
    author_id = serializers.UUIDField(write_only=True, required=True)

    tags = TagSerializer(many=True, read_only=True)
    tags_ids = serializers.ListField(
        child=serializers.UUIDField(), write_only=True, required=False
    )

    # embedding will be filled automatically later
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
            "metadata",
            "is_archived",
            "created_at",
            "updated_at",
            "tags",
            "tags_ids",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "version_number"]

    def create(self, validated_data):
        # Extract our custom fields
        tags_ids = validated_data.pop("tags_ids", [])
        node_type_id = validated_data.pop("node_type_id")
        author_id = validated_data.pop("author_id")

        # Create the node
        node = Node.objects.create(
            node_type_id=node_type_id, author_id=author_id, **validated_data
        )

        # Add tags if any were sent
        if tags_ids:
            node.tags.set(tags_ids)

        return node

    def update(self, instance, validated_data):
        # Same handling for updates
        tags_ids = validated_data.pop("tags_ids", None)
        node_type_id = validated_data.pop("node_type_id", None)
        author_id = validated_data.pop("author_id", None)

        # Update simple fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Update ForeignKeys if sent
        if node_type_id is not None:
            instance.node_type_id = node_type_id
        if author_id is not None:
            instance.author_id = author_id

        instance.save()

        # Update tags if sent
        if tags_ids is not None:
            instance.tags.set(tags_ids)

        return instance


class NodeRelationshipSerializer(serializers.ModelSerializer):
    source = serializers.UUIDField(source="source_id", write_only=True)
    target = serializers.UUIDField(source="target_id", write_only=True)
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
