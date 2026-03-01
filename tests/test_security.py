from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.cache import cache
from django.db.utils import OperationalError
from django.test import override_settings
from rest_framework.test import APIClient

from apps.users.models import Membership, Organization, User


def build_rest_framework_settings(auth_rate):
    return {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {
            **settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {}),
            "auth": auth_rate,
        },
    }


@pytest.mark.django_db
@override_settings(CORS_ALLOWED_ORIGINS=["http://localhost:5173"])
def test_cors_preflight_allows_configured_origin():
    client = APIClient()

    response = client.options(
        "/api/v1/auth/login/",
        HTTP_ORIGIN="http://localhost:5173",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
    )

    assert response.status_code == 200
    assert response["access-control-allow-origin"] == "http://localhost:5173"


@pytest.mark.django_db
@override_settings(REST_FRAMEWORK=build_rest_framework_settings("2/min"))
def test_login_endpoint_is_rate_limited():
    cache.clear()

    user = User.objects.create_user(email="limit@example.com", password="StrongPass123")
    organization = Organization.objects.create(name="Throttle", slug="throttle")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.SALES,
        is_default=True,
    )

    client = APIClient()
    payload = {"email": "limit@example.com", "password": "StrongPass123"}

    first = client.post("/api/v1/auth/login/", payload, format="json")
    second = client.post("/api/v1/auth/login/", payload, format="json")
    third = client.post("/api/v1/auth/login/", payload, format="json")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    cache.clear()


@pytest.mark.django_db
def test_readiness_returns_service_unavailable_when_database_is_down():
    class FailingConnection:
        def cursor(self):
            raise OperationalError("boom")

    client = APIClient()

    with patch("apps.core.views.connections", {"default": FailingConnection()}):
        response = client.get("/api/v1/health/ready/")

    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "unavailable"
