from django.urls import path

from . import views

app_name = "frontend"

urlpatterns = [
    path("", views.home, name="home"),
    path("nodes", views.node_list, name="nodes"),
    path("nodes/<uuid:pk>/", views.node_detail, name="node_detail"),
    path("set-theme/", views.set_theme, name="set_theme"),
]
