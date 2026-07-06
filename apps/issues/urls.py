from rest_framework.routers import DefaultRouter

from .views import IssueViewSet

router = DefaultRouter()
router.register("issues", IssueViewSet, basename="issue")

urlpatterns = router.urls
