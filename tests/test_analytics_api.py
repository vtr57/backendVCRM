import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.analytics.services import build_dashboard_data
from apps.leads.models import Lead, LeadSource
from apps.pipeline.models import Deal, Pipeline, Stage
from apps.pipeline.services import move_deal, record_initial_stage_movement
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


def create_deal(*, organization, lead, pipeline, stage, owner, created_by, amount, created_at=None, closed_at=None):
    deal = Deal.objects.create(
        organization=organization,
        lead=lead,
        pipeline=pipeline,
        stage=stage,
        title=f"Deal {lead.full_name}",
        amount=amount,
        owner=owner,
        created_by=created_by,
        position=stage.deals.count(),
        created_at=created_at or timezone.now(),
        closed_at=closed_at,
    )
    deal.sync_status_from_stage()
    deal.save()
    record_initial_stage_movement(deal)
    return deal


@pytest.mark.django_db
def test_dashboard_returns_main_kpis_and_charts():
    manager = User.objects.create_user(email="analytics@crm.com", password="StrongPass123")
    sales = User.objects.create_user(email="seller@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Acme", slug="acme")
    Membership.objects.create(
        user=manager,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )
    Membership.objects.create(
        user=sales,
        organization=organization,
        role=Membership.Role.SALES,
        is_default=True,
    )
    source = LeadSource.objects.create(name="Instagram", organization=organization)
    lead = Lead.objects.create(
        organization=organization,
        full_name="Lead Analytics",
        source=source,
        created_by=manager,
        assigned_to=sales,
    )
    pipeline = Pipeline.objects.get(organization=organization, is_default=True)
    open_stage = pipeline.stages.filter(kind=Stage.Kind.OPEN).order_by("order").first()
    won_stage = pipeline.stages.get(kind=Stage.Kind.WON)
    create_deal(
        organization=organization,
        lead=lead,
        pipeline=pipeline,
        stage=open_stage,
        owner=sales,
        created_by=manager,
        amount="3000.00",
    )
    won_deal = create_deal(
        organization=organization,
        lead=lead,
        pipeline=pipeline,
        stage=won_stage,
        owner=sales,
        created_by=manager,
        amount="5000.00",
        closed_at=timezone.now(),
    )

    client = auth_client_for(manager)
    response = client.get("/api/v1/analytics/dashboard/")

    assert response.status_code == 200
    body = response.json()
    assert body["kpis"]["total_leads"] == 1
    assert body["kpis"]["won_deals"] == 1
    assert body["kpis"]["closed_amount"] == "5000.00"
    assert body["kpis"]["open_pipeline_value"] == "3000.00"
    assert body["leads_by_source"][0]["source_name"] == "Instagram"
    assert body["won_amount_by_period"][0]["won_count"] == 1


@pytest.mark.django_db
def test_conversion_by_stage_report_uses_stage_history():
    manager = User.objects.create_user(email="stage-report@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Beta", slug="beta")
    Membership.objects.create(
        user=manager,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )
    lead = Lead.objects.create(organization=organization, full_name="Lead Stage", created_by=manager)
    pipeline = Pipeline.objects.get(organization=organization, is_default=True)
    first_stage = pipeline.stages.filter(kind=Stage.Kind.OPEN).order_by("order").first()
    won_stage = pipeline.stages.get(kind=Stage.Kind.WON)
    deal = create_deal(
        organization=organization,
        lead=lead,
        pipeline=pipeline,
        stage=first_stage,
        owner=manager,
        created_by=manager,
        amount="2500.00",
    )
    move_deal(
        deal=deal,
        target_stage=won_stage,
        moved_by=manager,
        target_position=0,
        note="Fechado",
    )

    client = auth_client_for(manager)
    response = client.get("/api/v1/analytics/reports/conversion-by-stage/")

    assert response.status_code == 200
    results = response.json()["results"]
    assert any(item["stage_name"] == first_stage.name for item in results)


@pytest.mark.django_db
def test_conversion_by_owner_and_source_profitability_reports():
    manager = User.objects.create_user(email="owner-report@crm.com", password="StrongPass123")
    seller = User.objects.create_user(email="owner-report-seller@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Gamma", slug="gamma")
    Membership.objects.create(
        user=manager,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )
    Membership.objects.create(
        user=seller,
        organization=organization,
        role=Membership.Role.SALES,
        is_default=True,
    )
    source = LeadSource.objects.create(name="WhatsApp", organization=organization)
    lead = Lead.objects.create(
        organization=organization,
        full_name="Lead Owner",
        source=source,
        created_by=manager,
        assigned_to=seller,
    )
    pipeline = Pipeline.objects.get(organization=organization, is_default=True)
    won_stage = pipeline.stages.get(kind=Stage.Kind.WON)
    create_deal(
        organization=organization,
        lead=lead,
        pipeline=pipeline,
        stage=won_stage,
        owner=seller,
        created_by=manager,
        amount="7800.00",
        closed_at=timezone.now(),
    )

    client = auth_client_for(manager)
    owner_response = client.get("/api/v1/analytics/reports/conversion-by-owner/")
    source_response = client.get("/api/v1/analytics/reports/source-profitability/")

    assert owner_response.status_code == 200
    assert source_response.status_code == 200
    assert owner_response.json()["results"][0]["owner_email"] == seller.email
    assert source_response.json()["results"][0]["source_name"] == "WhatsApp"
    assert source_response.json()["results"][0]["won_amount"] == "7800.00"


@pytest.mark.django_db
def test_sales_analytics_are_scoped_to_owned_pipeline_data():
    manager = User.objects.create_user(email="scope-manager@crm.com", password="StrongPass123")
    sales = User.objects.create_user(email="scope-sales@crm.com", password="StrongPass123")
    other = User.objects.create_user(email="scope-other@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Delta", slug="delta")
    Membership.objects.create(
        user=manager,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )
    Membership.objects.create(
        user=sales,
        organization=organization,
        role=Membership.Role.SALES,
        is_default=True,
    )
    Membership.objects.create(
        user=other,
        organization=organization,
        role=Membership.Role.SALES,
        is_default=True,
    )
    source = LeadSource.objects.create(name="Referral", organization=organization)
    visible_lead = Lead.objects.create(
        organization=organization,
        full_name="Visible Lead",
        source=source,
        created_by=manager,
        assigned_to=sales,
    )
    hidden_lead = Lead.objects.create(
        organization=organization,
        full_name="Hidden Lead",
        source=source,
        created_by=manager,
        assigned_to=other,
    )
    pipeline = Pipeline.objects.get(organization=organization, is_default=True)
    won_stage = pipeline.stages.get(kind=Stage.Kind.WON)
    create_deal(
        organization=organization,
        lead=visible_lead,
        pipeline=pipeline,
        stage=won_stage,
        owner=sales,
        created_by=manager,
        amount="4000.00",
        closed_at=timezone.now(),
    )
    create_deal(
        organization=organization,
        lead=hidden_lead,
        pipeline=pipeline,
        stage=won_stage,
        owner=other,
        created_by=manager,
        amount="9900.00",
        closed_at=timezone.now(),
    )

    client = auth_client_for(sales)
    response = client.get("/api/v1/analytics/reports/conversion-by-owner/")

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["owner_email"] == sales.email


@pytest.mark.django_db
def test_dashboard_service_uses_bounded_number_of_queries():
    manager = User.objects.create_user(email="perf@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Perf", slug="perf")
    membership = Membership.objects.create(
        user=manager,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )
    source = LeadSource.objects.create(name="Ads", organization=organization)
    pipeline = Pipeline.objects.get(organization=organization, is_default=True)
    open_stage = pipeline.stages.filter(kind=Stage.Kind.OPEN).order_by("order").first()
    won_stage = pipeline.stages.get(kind=Stage.Kind.WON)

    for index in range(5):
        lead = Lead.objects.create(
            organization=organization,
            full_name=f"Lead {index}",
            source=source,
            created_by=manager,
            assigned_to=manager,
        )
        create_deal(
            organization=organization,
            lead=lead,
            pipeline=pipeline,
            stage=won_stage if index % 2 == 0 else open_stage,
            owner=manager,
            created_by=manager,
            amount="1000.00",
            closed_at=timezone.now() if index % 2 == 0 else None,
        )

    with CaptureQueriesContext(connection) as ctx:
        build_dashboard_data(
            organization=organization,
            membership=membership,
            user=manager,
        )

    assert len(ctx.captured_queries) <= 8
