from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AuthorViewSet,
    NodeRelationshipViewSet,
    NodeTypeViewSet,
    NodeViewSet,
    TagViewSet,
)

router = DefaultRouter()
router.register(r"authors", AuthorViewSet)
router.register(r"nodetypes", NodeTypeViewSet)
router.register(r"tags", TagViewSet)
router.register(r"nodes", NodeViewSet)
router.register(r"relationships", NodeRelationshipViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
