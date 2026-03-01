from django.urls import path

from apps.analytics.views import (
    ConversionByOwnerAPIView,
    ConversionByStageAPIView,
    DashboardAPIView,
    SourceProfitabilityAPIView,
)

urlpatterns = [
    path("analytics/dashboard/", DashboardAPIView.as_view(), name="analytics-dashboard"),
    path(
        "analytics/reports/conversion-by-stage/",
        ConversionByStageAPIView.as_view(),
        name="analytics-conversion-by-stage",
    ),
    path(
        "analytics/reports/conversion-by-owner/",
        ConversionByOwnerAPIView.as_view(),
        name="analytics-conversion-by-owner",
    ),
    path(
        "analytics/reports/source-profitability/",
        SourceProfitabilityAPIView.as_view(),
        name="analytics-source-profitability",
    ),
]
