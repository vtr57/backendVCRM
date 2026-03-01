from django.urls import path

from apps.core.views import HealthcheckView, ReadinessView

urlpatterns = [
    path("health/", HealthcheckView.as_view(), name="healthcheck"),
    path("health/ready/", ReadinessView.as_view(), name="readiness"),
]
