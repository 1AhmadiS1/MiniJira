from rest_framework.routers import DefaultRouter

from .views import WorkspaceViewSet, WorkspaceMemberViewSet

router = DefaultRouter()
router.register("workspaces", WorkspaceViewSet, basename="workspace")
router.register("members", WorkspaceMemberViewSet, basename="workspacemember")

urlpatterns = router.urls
