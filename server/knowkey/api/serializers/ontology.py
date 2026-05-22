from rest_framework import serializers

from knowkey.core.models import NodeType, RelationshipType, Tag


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
