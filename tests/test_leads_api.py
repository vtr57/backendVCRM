import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.leads.models import Lead, LeadSource, Tag
from apps.users.models import Membership, Organization, User


def auth_client_for(user, organization_slug=None):
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {
            "email": user.email,
            "password": "StrongPass123",
        },
        format="json",
    ).json()
    headers = {"HTTP_AUTHORIZATION": f"Bearer {login['access']}"}
    if organization_slug:
        headers["HTTP_X_ORGANIZATION_SLUG"] = organization_slug
    client.credentials(**headers)
    return client


@pytest.mark.django_db
def test_manager_can_create_sources_tags_and_leads():
    user = User.objects.create_user(email="manager@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Acme", slug="acme")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )
    client = auth_client_for(user)

    source_response = client.post(
        "/api/v1/lead-sources/",
        {"name": "Instagram", "is_active": True},
        format="json",
    )
    tag_response = client.post(
        "/api/v1/tags/",
        {"name": "VIP", "color": "#111111"},
        format="json",
    )

    assert source_response.status_code == 201
    assert tag_response.status_code == 201

    lead_response = client.post(
        "/api/v1/leads/",
        {
            "full_name": "Maria Silva",
            "email": "maria@example.com",
            "phone": "11999999999",
            "company_name": "Acme Ltda",
            "source_id": source_response.json()["id"],
            "tag_ids": [tag_response.json()["id"]],
            "estimated_value": "3500,50",
        },
        format="json",
    )

    assert lead_response.status_code == 201
    lead = Lead.objects.get(full_name="Maria Silva")
    assert lead.status == Lead.Status.NEW
    assert lead.created_by_id == user.id
    assert lead.organization_id == organization.id
    assert str(lead.estimated_value) == "3500.50"
    assert list(lead.tags.values_list("name", flat=True)) == ["VIP"]


@pytest.mark.django_db
def test_sales_user_only_sees_owned_or_assigned_leads():
    sales = User.objects.create_user(email="sales@crm.com", password="StrongPass123")
    manager = User.objects.create_user(email="boss@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Beta", slug="beta")
    Membership.objects.create(
        user=sales,
        organization=organization,
        role=Membership.Role.SALES,
        is_default=True,
    )
    Membership.objects.create(
        user=manager,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )

    owned = Lead.objects.create(
        organization=organization,
        full_name="Owned Lead",
        created_by=sales,
    )
    assigned = Lead.objects.create(
        organization=organization,
        full_name="Assigned Lead",
        created_by=manager,
        assigned_to=sales,
    )
    Lead.objects.create(
        organization=organization,
        full_name="Hidden Lead",
        created_by=manager,
        assigned_to=manager,
    )

    client = auth_client_for(sales)
    response = client.get("/api/v1/leads/")

    assert response.status_code == 200
    returned_names = {item["full_name"] for item in response.json()["results"]}
    assert returned_names == {owned.full_name, assigned.full_name}


@pytest.mark.django_db
def test_lead_list_supports_search_filters_and_ordering():
    user = User.objects.create_user(email="manager2@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Gamma", slug="gamma")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )
    instagram = LeadSource.objects.create(name="Instagram", organization=organization)
    whatsapp = LeadSource.objects.create(name="WhatsApp", organization=organization)
    vip = Tag.objects.create(name="VIP", organization=organization)
    cold = Tag.objects.create(name="Cold", organization=organization)

    first = Lead.objects.create(
        organization=organization,
        full_name="Alice Johnson",
        email="alice@example.com",
        company_name="North LLC",
        created_by=user,
        source=instagram,
        status=Lead.Status.NEW,
        estimated_value="1500.00",
    )
    first.tags.add(vip)
    second = Lead.objects.create(
        organization=organization,
        full_name="Bruno Costa",
        email="bruno@example.com",
        company_name="South LLC",
        created_by=user,
        source=whatsapp,
        status=Lead.Status.CONTACTED,
        estimated_value="9000.00",
    )
    second.tags.add(cold)

    client = auth_client_for(user)
    response = client.get(
        "/api/v1/leads/",
        {
            "search": "Alice",
            "status": Lead.Status.NEW,
            "source": str(instagram.id),
            "tags": "VIP",
            "ordering": "-estimated_value",
        },
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["full_name"] == "Alice Johnson"


@pytest.mark.django_db
def test_delete_is_soft_delete_and_excludes_from_default_listing():
    user = User.objects.create_user(email="owner@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Delta", slug="delta")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.OWNER,
        is_default=True,
    )
    lead = Lead.objects.create(
        organization=organization,
        full_name="Soft Delete",
        created_by=user,
    )

    client = auth_client_for(user)
    delete_response = client.delete(f"/api/v1/leads/{lead.id}/")
    list_response = client.get("/api/v1/leads/")

    assert delete_response.status_code == 204
    lead.refresh_from_db()
    assert lead.deleted_at is not None
    assert list_response.json()["count"] == 0


@pytest.mark.django_db
def test_manager_can_bulk_delete_selected_leads():
    user = User.objects.create_user(email="owner-bulk@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Bulk", slug="bulk")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )
    first = Lead.objects.create(
        organization=organization,
        full_name="Lead One",
        created_by=user,
    )
    second = Lead.objects.create(
        organization=organization,
        full_name="Lead Two",
        created_by=user,
    )
    remaining = Lead.objects.create(
        organization=organization,
        full_name="Lead Three",
        created_by=user,
    )

    client = auth_client_for(user)
    response = client.post(
        "/api/v1/leads/bulk_delete/",
        {"lead_ids": [str(first.id), str(second.id)]},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["deleted_count"] == 2

    first.refresh_from_db()
    second.refresh_from_db()
    remaining.refresh_from_db()

    assert first.deleted_at is not None
    assert second.deleted_at is not None
    assert remaining.deleted_at is None


@pytest.mark.django_db
def test_import_csv_accepts_portuguese_template_columns():
    user = User.objects.create_user(email="importer@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Import", slug="import")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )

    client = auth_client_for(user)
    csv_file = SimpleUploadedFile(
        "leads.csv",
        "Nome,Email,Telefone,Empresa,Cargo,Fonte,Temperatura,Valor estimado,Origem\n"
        "Maria Silva,maria@example.com,11999999999,Acme Ltda,Compradora,Meta,quente,\"3500,50\",Instagram\n".encode(),
        content_type="text/csv",
    )
    mapping = {
        "full_name": "Nome",
        "email": "Email",
        "phone": "Telefone",
        "company_name": "Empresa",
        "job_title": "Cargo",
        "source_alias": "Fonte",
        "temperature": "Temperatura",
        "estimated_value": "Valor estimado",
        "source": "Origem",
    }

    response = client.post(
        "/api/v1/leads/import_csv/",
        {"file": csv_file, "mapping": json.dumps(mapping)},
    )

    assert response.status_code == 200
    assert response.json()["imported_count"] == 1

    lead = Lead.objects.get(full_name="Maria Silva")
    assert lead.email == "maria@example.com"
    assert lead.phone == "11999999999"
    assert lead.company_name == "Acme Ltda"
    assert lead.job_title == "Compradora"
    assert str(lead.estimated_value) == "3500.50"
    assert lead.temperature == Lead.Temperature.HOT
    assert lead.source.name == "Instagram"


@pytest.mark.django_db
def test_bulk_delete_rejects_inaccessible_leads_for_sales():
    sales = User.objects.create_user(email="sales-bulk@crm.com", password="StrongPass123")
    manager = User.objects.create_user(email="manager-bulk@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Theta", slug="theta")
    Membership.objects.create(
        user=sales,
        organization=organization,
        role=Membership.Role.SALES,
        is_default=True,
    )
    Membership.objects.create(
        user=manager,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )
    visible = Lead.objects.create(
        organization=organization,
        full_name="Visible Lead",
        created_by=sales,
    )
    hidden = Lead.objects.create(
        organization=organization,
        full_name="Hidden Lead",
        created_by=manager,
        assigned_to=manager,
    )

    client = auth_client_for(sales)
    response = client.post(
        "/api/v1/leads/bulk_delete/",
        {"lead_ids": [str(visible.id), str(hidden.id)]},
        format="json",
    )

    assert response.status_code == 404
    visible.refresh_from_db()
    hidden.refresh_from_db()
    assert visible.deleted_at is None
    assert hidden.deleted_at is None


@pytest.mark.django_db
def test_sales_cannot_manage_lead_settings():
    user = User.objects.create_user(email="sales2@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Epsilon", slug="epsilon")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.SALES,
        is_default=True,
    )

    client = auth_client_for(user)
    response = client.post(
        "/api/v1/tags/",
        {"name": "Blocked", "color": "#000000"},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_sales_can_list_tags_and_sources_for_lead_forms():
    user = User.objects.create_user(email="sales-read@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Eta", slug="eta")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.SALES,
        is_default=True,
    )
    LeadSource.objects.create(name="Referral", organization=organization)
    Tag.objects.create(name="Important", organization=organization)

    client = auth_client_for(user)
    sources_response = client.get("/api/v1/lead-sources/")
    tags_response = client.get("/api/v1/tags/")

    assert sources_response.status_code == 200
    assert tags_response.status_code == 200
    assert sources_response.json()["count"] == 1
    assert tags_response.json()["count"] == 1


@pytest.mark.django_db
def test_sales_cannot_update_unrelated_lead():
    sales = User.objects.create_user(email="sales3@crm.com", password="StrongPass123")
    manager = User.objects.create_user(email="manager3@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Zeta", slug="zeta")
    Membership.objects.create(
        user=sales,
        organization=organization,
        role=Membership.Role.SALES,
        is_default=True,
    )
    Membership.objects.create(
        user=manager,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )
    lead = Lead.objects.create(
        organization=organization,
        full_name="Protected Lead",
        created_by=manager,
        assigned_to=manager,
    )

    client = auth_client_for(sales)
    response = client.patch(
        f"/api/v1/leads/{lead.id}/",
        {"full_name": "Mutated"},
        format="json",
    )

    assert response.status_code == 404
