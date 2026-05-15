from django.contrib import admin

from .models import Author, Node, NodeRelationship, NodeType, Tag


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ["name", "author_type", "created_at"]
    search_fields = ["name"]
    list_filter = ["author_type"]


@admin.register(NodeType)
class NodeTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "icon", "color"]
    search_fields = ["name", "description"]


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "color"]
    search_fields = ["name"]


@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "node_type",
        "author",
        "version_number",
        "is_archived",
        "created_at",
    ]
    list_filter = ["node_type", "is_archived", "author"]
    search_fields = ["title", "summary", "content"]
    readonly_fields = ["created_at", "updated_at"]
    filter_horizontal = ["tags"]  # nice UI for tags


@admin.register(NodeRelationship)
class NodeRelationshipAdmin(admin.ModelAdmin):
    list_display = ["source", "relationship_type", "target", "weight", "created_at"]
    list_filter = ["relationship_type"]
    search_fields = ["source__title", "target__title"]
