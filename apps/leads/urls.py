from rest_framework.routers import DefaultRouter

from apps.leads.views import LeadSourceViewSet, LeadViewSet, TagViewSet

router = DefaultRouter()
router.register("leads", LeadViewSet, basename="lead")
router.register("lead-sources", LeadSourceViewSet, basename="lead-source")
router.register("tags", TagViewSet, basename="tag")

urlpatterns = router.urls
