from rest_framework.routers import DefaultRouter

from apps.interactions.views import InteractionViewSet

router = DefaultRouter()
router.register("interactions", InteractionViewSet, basename="interaction")

urlpatterns = router.urls
