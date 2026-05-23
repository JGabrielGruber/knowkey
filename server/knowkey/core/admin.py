from django.contrib import admin
from knowkey.core.models.ontology import RelationshipType

from .models import Author, Node, NodeRelationship, NodeType, Tag


# ====================== CUSTOM FILTERS ======================
class IsLatestFilter(admin.SimpleListFilter):
    title = "is latest"
    parameter_name = "is_latest"

    def lookups(self, request, model_admin):
        return (
            ("yes", "Yes (live head)"),
            ("no", "No (historical snapshot)"),
        )

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(version_of__isnull=True)
        if self.value() == "no":
            return queryset.filter(version_of__isnull=False)
        return queryset


# ====================== INLINES ======================
class NodeVersionInline(admin.TabularInline):
    model = Node
    fk_name = "version_of"
    fields = ["version_number", "title", "created_at", "author"]
    readonly_fields = ["version_number", "title", "created_at", "author"]
    extra = 0
    can_delete = False
    ordering = ["-version_number"]
    verbose_name = "Historical Version"
    verbose_name_plural = "Historical Versions"


class OutgoingRelationshipInline(admin.TabularInline):
    model = NodeRelationship
    fk_name = "source"
    fields = ["relationship_type", "target", "weight", "created_by", "created_at"]
    readonly_fields = ["created_at"]
    extra = 1
    verbose_name = "Outgoing Relationship"


class IncomingRelationshipInline(admin.TabularInline):
    model = NodeRelationship
    fk_name = "target"
    fields = ["source", "relationship_type", "weight", "created_by", "created_at"]
    readonly_fields = ["created_at"]
    extra = 0
    can_delete = False
    verbose_name = "Incoming Relationship"


# ====================== MODEL ADMINS ======================
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
        "is_latest",
        "is_archived",
        "created_at",
    ]
    list_filter = [
        "node_type",
        "is_archived",
        "author",
        IsLatestFilter,
    ]
    search_fields = ["title", "summary", "content"]
    readonly_fields = [
        "created_at",
        "updated_at",
        "version_of",
        "version_number",
        "embedding",
    ]
    filter_horizontal = ["tags"]

    inlines = [
        NodeVersionInline,
        OutgoingRelationshipInline,
        IncomingRelationshipInline,
    ]

    # ====================== RICH ADMIN ACTIONS ======================
    actions = ["force_create_snapshot", "revert_to_version"]

    @admin.action(description="📸 Force create snapshot (for testing/debug)")
    def force_create_snapshot(self, request, queryset):
        count = 0
        for node in queryset.filter(version_of__isnull=True):
            node.create_manual_snapshot()
            count += 1
        self.message_user(request, f"✅ Created {count} manual snapshot(s).")

    @admin.action(
        description="🔄 Revert live node to this historical snapshot",
        permissions=["change"],
    )
    def revert_to_version(self, request, queryset):
        """One-click full undo (content + relationships)"""
        reverted = 0
        for snapshot in queryset.filter(version_of__isnull=False):
            try:
                live_node = snapshot.version_of
                live_node.revert_to(snapshot)  # author=None is fine here
                reverted += 1
            except Exception as e:
                self.message_user(
                    request, f"❌ Failed to revert {snapshot.title}: {e}", level="ERROR"
                )
        if reverted:
            self.message_user(request, f"✅ Successfully reverted {reverted} node(s).")

    # Protect historical snapshots from accidental editing
    def get_readonly_fields(self, request, obj=None):
        readonly = super().get_readonly_fields(request, obj)
        if obj and obj.version_of is not None:  # snapshot
            extra = [
                "title",
                "summary",
                "content",
                "node_type",
                "author",
                "metadata",
                "is_archived",
                "tags",
            ]
            return list(readonly) + extra
        return readonly

    def is_latest(self, obj):
        return obj.version_of is None

    is_latest.boolean = True
    is_latest.short_description = "Live Head"


@admin.register(RelationshipType)
class RelationshipTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "icon", "color"]
    search_fields = ["name", "description"]


@admin.register(NodeRelationship)
class NodeRelationshipAdmin(admin.ModelAdmin):
    list_display = [
        "source",
        "relationship_type",
        "target",
        "weight",
        "created_at",
        "source_is_latest",
        "target_is_latest",
    ]
    list_filter = ["relationship_type", IsLatestFilter]
    search_fields = ["source__title", "target__title"]

    def source_is_latest(self, obj):
        return obj.source.version_of is None

    source_is_latest.boolean = True
    source_is_latest.short_description = "Source Live?"

    def target_is_latest(self, obj):
        return obj.target.version_of is None

    target_is_latest.boolean = True
    target_is_latest.short_description = "Target Live?"
