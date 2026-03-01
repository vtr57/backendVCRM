from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from apps.analytics.permissions import AnalyticsAccessPermission
from apps.analytics.serializers import (
    AnalyticsQuerySerializer,
    DashboardSerializer,
    OwnerConversionReportSerializer,
    SourceProfitabilityReportSerializer,
    StageConversionReportSerializer,
)
from apps.analytics.services import (
    build_conversion_by_owner_report,
    build_conversion_by_stage_report,
    build_dashboard_data,
    build_source_profitability_report,
)


class AnalyticsBaseAPIView(GenericAPIView):
    permission_classes = [AnalyticsAccessPermission]
    query_serializer_class = AnalyticsQuerySerializer

    def get_query_data(self, request):
        data = request.query_params.copy()
        if "from" in data and "from_date" not in data:
            data["from_date"] = data["from"]
        if "to" in data and "to_date" not in data:
            data["to_date"] = data["to"]
        serializer = self.query_serializer_class(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def get_service_kwargs(self, request):
        query_data = self.get_query_data(request)
        return {
            "organization": request.organization,
            "membership": request.membership,
            "user": request.user,
            "date_from": query_data.get("from"),
            "date_to": query_data.get("to"),
            "pipeline_id": query_data.get("pipeline_id"),
        }


class DashboardAPIView(AnalyticsBaseAPIView):
    def get(self, request):
        data = build_dashboard_data(**self.get_service_kwargs(request))
        return Response(DashboardSerializer(data).data)


class ConversionByStageAPIView(AnalyticsBaseAPIView):
    def get(self, request):
        data = build_conversion_by_stage_report(**self.get_service_kwargs(request))
        return Response(StageConversionReportSerializer(data).data)


class ConversionByOwnerAPIView(AnalyticsBaseAPIView):
    def get(self, request):
        data = build_conversion_by_owner_report(**self.get_service_kwargs(request))
        return Response(OwnerConversionReportSerializer(data).data)


class SourceProfitabilityAPIView(AnalyticsBaseAPIView):
    def get(self, request):
        data = build_source_profitability_report(**self.get_service_kwargs(request))
        return Response(SourceProfitabilityReportSerializer(data).data)
