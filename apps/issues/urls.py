from rest_framework.routers import DefaultRouter

from .views import IssueViewSet, CommentViewSet, AttachmentViewSet

router = DefaultRouter()
router.register("issues", IssueViewSet, basename="issue")
router.register("comments", CommentViewSet, basename="comment")
router.register("attachments", AttachmentViewSet, basename="attachment")

urlpatterns = router.urls
