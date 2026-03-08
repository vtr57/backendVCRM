import pytest
from rest_framework.test import APIClient

from apps.leads.models import Lead
from apps.pipeline.models import Deal, Pipeline, Stage, StageMovement
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
def test_organization_creation_creates_default_pipeline_with_stages():
    organization = Organization.objects.create(name="Acme", slug="acme")

    pipeline = Pipeline.objects.get(organization=organization, is_default=True)

    assert pipeline.name == "Pipeline Principal"
    assert pipeline.stages.count() == 6
    assert pipeline.stages.filter(kind=Stage.Kind.OPEN).count() == 4


@pytest.mark.django_db
def test_deal_create_uses_default_pipeline_and_first_stage():
    user = User.objects.create_user(email="manager-pipeline@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Beta", slug="beta")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )
    lead = Lead.objects.create(
        organization=organization,
        full_name="Lead Pipeline",
        created_by=user,
        assigned_to=user,
    )

    client = auth_client_for(user)
    response = client.post(
        "/api/v1/deals/",
        {
            "lead_id": str(lead.id),
            "title": "Plano Anual",
            "amount": "12000.00",
        },
        format="json",
    )

    assert response.status_code == 201
    body = response.json()
    default_pipeline = Pipeline.objects.get(organization=organization, is_default=True)
    first_stage = default_pipeline.stages.filter(kind=Stage.Kind.OPEN).order_by("order").first()
    deal = Deal.objects.get(id=body["id"])

    assert deal.pipeline_id == default_pipeline.id
    assert deal.stage_id == first_stage.id
    assert deal.status == Deal.Status.OPEN
    assert lead.deals.count() == 1


@pytest.mark.django_db
def test_board_returns_stages_with_nested_deals():
    user = User.objects.create_user(email="board@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Gamma", slug="gamma")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )
    lead = Lead.objects.create(
        organization=organization,
        full_name="Cliente Board",
        company_name="Gamma Ltd",
        created_by=user,
        assigned_to=user,
    )
    pipeline = Pipeline.objects.get(organization=organization, is_default=True)
    first_stage = pipeline.stages.filter(kind=Stage.Kind.OPEN).order_by("order").first()
    Deal.objects.create(
        organization=organization,
        lead=lead,
        pipeline=pipeline,
        stage=first_stage,
        title="Contrato Board",
        amount="5000.00",
        owner=user,
        created_by=user,
        position=0,
    )

    client = auth_client_for(user)
    response = client.get("/api/v1/pipelines/board/")

    assert response.status_code == 200
    body = response.json()
    assert body["pipeline"]["id"] == str(pipeline.id)
    assert len(body["stages"]) == 6
    assert body["stages"][0]["deals"][0]["title"] == "Contrato Board"


@pytest.mark.django_db
def test_manager_board_returns_only_selected_team_member_deals():
    manager = User.objects.create_user(email="manager-scope@crm.com", password="StrongPass123")
    sales_a = User.objects.create_user(email="sales-a@crm.com", password="StrongPass123")
    sales_b = User.objects.create_user(email="sales-b@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Scoped Org", slug="scoped-org")
    Membership.objects.create(
        user=manager,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )
    Membership.objects.create(
        user=sales_a,
        organization=organization,
        role=Membership.Role.SALES,
        is_default=True,
    )
    Membership.objects.create(
        user=sales_b,
        organization=organization,
        role=Membership.Role.SALES,
        is_default=True,
    )
    pipeline = Pipeline.objects.get(organization=organization, is_default=True)
    first_stage = pipeline.stages.filter(kind=Stage.Kind.OPEN).order_by("order").first()
    lead_a = Lead.objects.create(
        organization=organization,
        full_name="Lead Sales A",
        created_by=manager,
        assigned_to=sales_a,
    )
    lead_b = Lead.objects.create(
        organization=organization,
        full_name="Lead Sales B",
        created_by=manager,
        assigned_to=sales_b,
    )
    Deal.objects.create(
        organization=organization,
        lead=lead_a,
        pipeline=pipeline,
        stage=first_stage,
        title="Negócio Sales A",
        amount="3000.00",
        owner=sales_a,
        created_by=manager,
        position=0,
    )
    Deal.objects.create(
        organization=organization,
        lead=lead_b,
        pipeline=pipeline,
        stage=first_stage,
        title="Negócio Sales B",
        amount="4200.00",
        owner=sales_b,
        created_by=manager,
        position=1,
    )

    client = auth_client_for(manager)
    response = client.get(f"/api/v1/pipelines/board/?member_user_id={sales_a.id}")

    assert response.status_code == 200
    deals = response.json()["stages"][0]["deals"]
    assert [deal["title"] for deal in deals] == ["Negócio Sales A"]


@pytest.mark.django_db
def test_pipeline_create_seeds_default_stages():
    user = User.objects.create_user(email="pipeline-create@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Create Pipeline", slug="create-pipeline")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )

    client = auth_client_for(user)
    response = client.post(
        "/api/v1/pipelines/",
        {
            "name": "Expansão",
            "is_default": False,
            "is_active": True,
        },
        format="json",
    )

    assert response.status_code == 201
    pipeline = Pipeline.objects.get(id=response.json()["id"])
    assert pipeline.stages.count() == 6


@pytest.mark.django_db
def test_move_endpoint_updates_deal_and_lead_status_and_records_history():
    user = User.objects.create_user(email="move@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Delta", slug="delta")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )
    lead = Lead.objects.create(
        organization=organization,
        full_name="Lead Move",
        created_by=user,
        assigned_to=user,
    )
    pipeline = Pipeline.objects.get(organization=organization, is_default=True)
    first_stage = pipeline.stages.filter(kind=Stage.Kind.OPEN).order_by("order").first()
    won_stage = pipeline.stages.get(kind=Stage.Kind.WON)
    deal = Deal.objects.create(
        organization=organization,
        lead=lead,
        pipeline=pipeline,
        stage=first_stage,
        title="Fechamento",
        amount="2000.00",
        owner=user,
        created_by=user,
        position=0,
    )

    client = auth_client_for(user)
    response = client.post(
        f"/api/v1/deals/{deal.id}/move/",
        {
            "stage_id": str(won_stage.id),
            "position": 0,
            "note": "Negócio fechado",
        },
        format="json",
    )

    assert response.status_code == 200
    deal.refresh_from_db()
    lead.refresh_from_db()

    assert deal.stage_id == won_stage.id
    assert deal.status == Deal.Status.WON
    assert deal.closed_at is not None
    assert lead.status == Lead.Status.WON
    movement = StageMovement.objects.get(deal=deal)
    assert movement.to_stage_id == won_stage.id
    assert movement.note == "Negócio fechado"


@pytest.mark.django_db
def test_move_to_lost_requires_reason():
    user = User.objects.create_user(email="lost@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Epsilon", slug="epsilon")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )
    lead = Lead.objects.create(
        organization=organization,
        full_name="Lead Lost",
        created_by=user,
        assigned_to=user,
    )
    pipeline = Pipeline.objects.get(organization=organization, is_default=True)
    first_stage = pipeline.stages.filter(kind=Stage.Kind.OPEN).order_by("order").first()
    lost_stage = pipeline.stages.get(kind=Stage.Kind.LOST)
    deal = Deal.objects.create(
        organization=organization,
        lead=lead,
        pipeline=pipeline,
        stage=first_stage,
        title="Negócio Perdido",
        amount="1000.00",
        owner=user,
        created_by=user,
        position=0,
    )

    client = auth_client_for(user)
    response = client.post(
        f"/api/v1/deals/{deal.id}/move/",
        {"stage_id": str(lost_stage.id)},
        format="json",
    )

    assert response.status_code == 400
    assert "lost_reason" in response.json()


@pytest.mark.django_db
def test_delete_deal_removes_only_deal_and_keeps_lead():
    user = User.objects.create_user(email="delete-deal@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Delete Deal", slug="delete-deal")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )
    lead = Lead.objects.create(
        organization=organization,
        full_name="Lead Mantido",
        created_by=user,
        assigned_to=user,
    )
    pipeline = Pipeline.objects.get(organization=organization, is_default=True)
    first_stage = pipeline.stages.filter(kind=Stage.Kind.OPEN).order_by("order").first()
    deal = Deal.objects.create(
        organization=organization,
        lead=lead,
        pipeline=pipeline,
        stage=first_stage,
        title="Deal Removido",
        amount="3200.00",
        owner=user,
        created_by=user,
        position=0,
    )

    client = auth_client_for(user)
    response = client.delete(f"/api/v1/deals/{deal.id}/")

    assert response.status_code == 204
    assert not Deal.objects.filter(id=deal.id).exists()
    assert Lead.objects.filter(id=lead.id).exists()


@pytest.mark.django_db
def test_sales_board_only_returns_owned_or_assigned_deals():
    sales = User.objects.create_user(email="sales-board@crm.com", password="StrongPass123")
    manager = User.objects.create_user(email="manager-board@crm.com", password="StrongPass123")
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
    pipeline = Pipeline.objects.get(organization=organization, is_default=True)
    first_stage = pipeline.stages.filter(kind=Stage.Kind.OPEN).order_by("order").first()
    visible_lead = Lead.objects.create(
        organization=organization,
        full_name="Lead Visível",
        created_by=manager,
        assigned_to=sales,
    )
    hidden_lead = Lead.objects.create(
        organization=organization,
        full_name="Lead Oculto",
        created_by=manager,
        assigned_to=manager,
    )
    Deal.objects.create(
        organization=organization,
        lead=visible_lead,
        pipeline=pipeline,
        stage=first_stage,
        title="Negócio Visível",
        amount="4000.00",
        owner=sales,
        created_by=manager,
        position=0,
    )
    Deal.objects.create(
        organization=organization,
        lead=hidden_lead,
        pipeline=pipeline,
        stage=first_stage,
        title="Negócio Oculto",
        amount="9000.00",
        owner=manager,
        created_by=manager,
        position=1,
    )

    client = auth_client_for(sales)
    response = client.get("/api/v1/pipelines/board/")

    assert response.status_code == 200
    deals = response.json()["stages"][0]["deals"]
    assert [deal["title"] for deal in deals] == ["Negócio Visível"]


@pytest.mark.django_db
def test_sales_board_ignores_team_member_filter_and_keeps_own_scope():
    sales = User.objects.create_user(email="sales-scope@crm.com", password="StrongPass123")
    other_sales = User.objects.create_user(email="sales-other@crm.com", password="StrongPass123")
    manager = User.objects.create_user(email="manager-scope-2@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Theta", slug="theta")
    Membership.objects.create(
        user=sales,
        organization=organization,
        role=Membership.Role.SALES,
        is_default=True,
    )
    Membership.objects.create(
        user=other_sales,
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
    pipeline = Pipeline.objects.get(organization=organization, is_default=True)
    first_stage = pipeline.stages.filter(kind=Stage.Kind.OPEN).order_by("order").first()
    own_lead = Lead.objects.create(
        organization=organization,
        full_name="Lead Próprio",
        created_by=manager,
        assigned_to=sales,
    )
    other_lead = Lead.objects.create(
        organization=organization,
        full_name="Lead de Outro",
        created_by=manager,
        assigned_to=other_sales,
    )
    Deal.objects.create(
        organization=organization,
        lead=own_lead,
        pipeline=pipeline,
        stage=first_stage,
        title="Negócio Próprio",
        amount="1500.00",
        owner=sales,
        created_by=manager,
        position=0,
    )
    Deal.objects.create(
        organization=organization,
        lead=other_lead,
        pipeline=pipeline,
        stage=first_stage,
        title="Negócio de Outro",
        amount="1800.00",
        owner=other_sales,
        created_by=manager,
        position=1,
    )

    client = auth_client_for(sales)
    response = client.get(f"/api/v1/pipelines/board/?member_user_id={other_sales.id}")

    assert response.status_code == 200
    deals = response.json()["stages"][0]["deals"]
    assert [deal["title"] for deal in deals] == ["Negócio Próprio"]
