from django.db import connections
from django.db.utils import OperationalError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthcheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok", "service": "crm-api"})


class ReadinessView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except OperationalError:
            return Response(
                {
                    "status": "error",
                    "service": "crm-api",
                    "checks": {"database": "unavailable"},
                },
                status=503,
            )

        return Response(
            {
                "status": "ok",
                "service": "crm-api",
                "checks": {"database": "ok"},
            }
        )
