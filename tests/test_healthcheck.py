from rest_framework.test import APIClient


def test_healthcheck_returns_ok():
    client = APIClient()

    response = client.get("/api/v1/health/")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_returns_database_ok():
    client = APIClient()

    response = client.get("/api/v1/health/ready/")

    assert response.status_code == 200
    assert response.json()["checks"]["database"] == "ok"
