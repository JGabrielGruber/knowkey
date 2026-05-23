from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from knowkey.core.models import Node


def home(request):
    """Clean landing page"""
    return render(request, "web/home.html")


def node_list(request):
    """Main listing page with tabs"""
    query = request.GET.get("q", "")
    node_type = request.GET.get("node_type", "")
    tag = request.GET.get("tag", "")
    view_mode = request.GET.get("view", "list")  # list or graph

    queryset = (
        Node.objects.latest_versions()
        .select_related("node_type", "author")
        .prefetch_related("tags")
    )

    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(summary__icontains=query)
            | Q(content__icontains=query)
        )

    if node_type:
        queryset = queryset.filter(node_type__name__iexact=node_type)

    if tag:
        queryset = queryset.filter(tags__name__iexact=tag)

    nodes = queryset.order_by("-updated_at")[:120]

    context = {
        "nodes": nodes,
        "query": query,
        "selected_node_type": node_type,
        "selected_tag": tag,
        "view_mode": view_mode,
        "node_types": Node.objects.values_list("node_type__name", flat=True)
        .distinct()
        .order_by("node_type__name"),
        "tags": Node.objects.values_list("tags__name", flat=True)
        .distinct()
        .exclude(tags__name__isnull=True)
        .order_by("tags__name"),
    }

    if view_mode == "graph":
        context["graph_data"] = get_graph_data(nodes)

    return render(request, "web/nodes/list.html", context)


def get_graph_data(nodes):
    elements = []
    node_ids = {str(node.id) for node in nodes}

    for node in nodes:
        elements.append(
            {
                "data": {
                    "id": str(node.id),
                    "label": node.title[:40],
                    "type": node.node_type.name,
                    "summary": node.summary[:100],
                }
            }
        )

        for rel in node.outgoing_relationships.select_related(
            "target", "relationship_type"
        )[:15]:
            if str(rel.target.id) in node_ids:
                elements.append(
                    {
                        "data": {
                            "id": f"e{rel.id}",
                            "source": str(rel.source_id),
                            "target": str(rel.target_id),
                            "label": rel.relationship_type.name,
                        }
                    }
                )
    return elements


def node_detail(request, pk):
    node = get_object_or_404(
        Node.objects.select_related("node_type", "author").prefetch_related(
            "tags", "outgoing_relationships__target", "incoming_relationships__source"
        ),
        pk=pk,
    )
    return render(request, "web/nodes/detail.html", {"node": node})
