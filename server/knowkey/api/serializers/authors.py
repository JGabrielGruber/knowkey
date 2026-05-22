from rest_framework import serializers

from knowkey.core.models import Author


class AuthorSerializer(serializers.ModelSerializer):
    author_type_display = serializers.CharField(
        source="get_author_type_display", read_only=True
    )

    class Meta:
        model = Author
        fields = ["id", "name", "author_type", "author_type_display", "created_at"]
