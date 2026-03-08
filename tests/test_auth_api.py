import pytest
from rest_framework.test import APIClient

from apps.users.models import Membership, Organization, User


@pytest.mark.django_db
def test_register_creates_user_organization_and_owner_membership():
    client = APIClient()

    response = client.post(
        "/api/v1/auth/register/",
        {
            "email": "owner@example.com",
            "first_name": "Owner",
            "last_name": "User",
            "password": "StrongPass123",
            "password_confirm": "StrongPass123",
            "organization_name": "Acme CRM",
        },
        format="json",
    )

    assert response.status_code == 201
    body = response.json()

    user = User.objects.get(email="owner@example.com")
    membership = Membership.objects.select_related("organization").get(user=user)

    assert body["access"]
    assert body["refresh"]
    assert body["user"]["email"] == "owner@example.com"
    assert membership.role == Membership.Role.OWNER
    assert membership.is_default is True
    assert membership.organization.slug == "acme-crm"


@pytest.mark.django_db
def test_login_returns_tokens_and_user_memberships():
    user = User.objects.create_user(
        email="sales@example.com",
        password="StrongPass123",
        first_name="Sales",
    )
    organization = Organization.objects.create(name="Northwind", slug="northwind")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.SALES,
        is_default=True,
    )

    client = APIClient()
    response = client.post(
        "/api/v1/auth/login/",
        {
            "email": "sales@example.com",
            "password": "StrongPass123",
        },
        format="json",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access"]
    assert body["refresh"]
    assert body["user"]["memberships"][0]["organization"]["slug"] == "northwind"


@pytest.mark.django_db
def test_refresh_returns_new_access_token():
    user = User.objects.create_user(email="refresh@example.com", password="StrongPass123")
    organization = Organization.objects.create(name="Refresh Org", slug="refresh-org")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.SALES,
        is_default=True,
    )

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {
            "email": "refresh@example.com",
            "password": "StrongPass123",
        },
        format="json",
    )

    response = client.post(
        "/api/v1/auth/refresh/",
        {"refresh": login.json()["refresh"]},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["access"]


@pytest.mark.django_db
def test_me_uses_default_membership_when_no_header_is_present():
    user = User.objects.create_user(email="manager@example.com", password="StrongPass123")
    organization = Organization.objects.create(name="Umbrella", slug="umbrella")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {
            "email": "manager@example.com",
            "password": "StrongPass123",
        },
        format="json",
    ).json()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login['access']}")

    response = client.get("/api/v1/auth/me/")

    assert response.status_code == 200
    body = response.json()
    assert body["organization"]["slug"] == "umbrella"
    assert body["user"]["current_membership"]["role"] == Membership.Role.MANAGER


@pytest.mark.django_db
def test_me_resolves_organization_from_slug_header():
    user = User.objects.create_user(email="admin@example.com", password="StrongPass123")
    default_org = Organization.objects.create(name="Alpha", slug="alpha")
    selected_org = Organization.objects.create(name="Beta", slug="beta")
    Membership.objects.create(
        user=user,
        organization=default_org,
        role=Membership.Role.ADMIN,
        is_default=True,
    )
    Membership.objects.create(
        user=user,
        organization=selected_org,
        role=Membership.Role.ADMIN,
    )

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {
            "email": "admin@example.com",
            "password": "StrongPass123",
        },
        format="json",
    ).json()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {login['access']}",
        HTTP_X_ORGANIZATION_SLUG="beta",
    )

    response = client.get("/api/v1/auth/me/")

    assert response.status_code == 200
    body = response.json()
    assert body["organization"]["slug"] == "beta"
    assert body["user"]["current_membership"]["organization"]["slug"] == "beta"


@pytest.mark.django_db
def test_me_rejects_organization_without_membership():
    user = User.objects.create_user(email="outside@example.com", password="StrongPass123")
    default_org = Organization.objects.create(name="Inside", slug="inside")
    foreign_org = Organization.objects.create(name="Outside", slug="outside")
    Membership.objects.create(
        user=user,
        organization=default_org,
        role=Membership.Role.SALES,
        is_default=True,
    )

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {
            "email": "outside@example.com",
            "password": "StrongPass123",
        },
        format="json",
    ).json()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {login['access']}",
        HTTP_X_ORGANIZATION_SLUG=foreign_org.slug,
    )

    response = client.get("/api/v1/auth/me/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_me_returns_404_for_unknown_organization_header():
    user = User.objects.create_user(email="missing@example.com", password="StrongPass123")
    organization = Organization.objects.create(name="Known", slug="known")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.SALES,
        is_default=True,
    )

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {
            "email": "missing@example.com",
            "password": "StrongPass123",
        },
        format="json",
    ).json()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {login['access']}",
        HTTP_X_ORGANIZATION_SLUG="unknown-org",
    )

    response = client.get("/api/v1/auth/me/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_team_members_returns_active_members_for_selected_organization():
    requester = User.objects.create_user(email="owner@team.com", password="StrongPass123", first_name="Owner")
    teammate = User.objects.create_user(email="sales@team.com", password="StrongPass123", first_name="Sales")
    outsider = User.objects.create_user(email="outsider@team.com", password="StrongPass123", first_name="Out")
    organization = Organization.objects.create(name="Team Org", slug="team-org")
    other_organization = Organization.objects.create(name="Other Org", slug="other-org")
    Membership.objects.create(
        user=requester,
        organization=organization,
        role=Membership.Role.OWNER,
        is_default=True,
    )
    Membership.objects.create(
        user=teammate,
        organization=organization,
        role=Membership.Role.SALES,
    )
    Membership.objects.create(
        user=outsider,
        organization=other_organization,
        role=Membership.Role.SALES,
        is_default=True,
    )

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {
            "email": "owner@team.com",
            "password": "StrongPass123",
        },
        format="json",
    ).json()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login['access']}")

    response = client.get("/api/v1/auth/team-members/")

    assert response.status_code == 200
    body = response.json()
    assert [member["email"] for member in body] == ["owner@team.com", "sales@team.com"]
