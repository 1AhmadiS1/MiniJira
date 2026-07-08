from rest_framework.routers import DefaultRouter

from .views import IssueViewSet, CommentViewSet

router = DefaultRouter()
router.register("issues", IssueViewSet, basename="issue")
router.register("comments", CommentViewSet, basename="comment")

urlpatterns = router.urls
