from django.shortcuts import render

from .nodes import get_graph_data, node_detail, node_list
from .theme import set_theme


def home(request):
    """Clean landing page"""
    return render(request, "web/home.html")
