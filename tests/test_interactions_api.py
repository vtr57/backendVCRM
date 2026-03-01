from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.interactions.models import Interaction
from apps.leads.models import Lead
from apps.pipeline.models import Deal, Pipeline, Stage
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
def test_create_call_interaction_updates_lead_last_interaction():
    user = User.objects.create_user(email="call@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Acme", slug="acme")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )
    lead = Lead.objects.create(
        organization=organization,
        full_name="Lead Call",
        created_by=user,
        assigned_to=user,
    )

    client = auth_client_for(user)
    response = client.post(
        "/api/v1/interactions/",
        {
            "lead_id": str(lead.id),
            "type": Interaction.Type.CALL,
            "direction": Interaction.Direction.OUTBOUND,
            "subject": "Primeira ligação",
            "content": "Ligação para entender a necessidade do cliente.",
            "outcome": "Contato realizado",
        },
        format="json",
    )

    assert response.status_code == 201
    lead.refresh_from_db()
    assert lead.last_interaction_at is not None
    assert Interaction.objects.get(id=response.json()["id"]).type == Interaction.Type.CALL


@pytest.mark.django_db
def test_create_note_interaction_forces_internal_direction():
    user = User.objects.create_user(email="note@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Beta", slug="beta")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )
    lead = Lead.objects.create(
        organization=organization,
        full_name="Lead Note",
        created_by=user,
    )

    client = auth_client_for(user)
    response = client.post(
        "/api/v1/interactions/",
        {
            "lead_id": str(lead.id),
            "type": Interaction.Type.NOTE,
            "direction": Interaction.Direction.OUTBOUND,
            "content": "Observação interna sobre urgência.",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["direction"] == Interaction.Direction.INTERNAL


@pytest.mark.django_db
def test_message_requires_non_internal_direction():
    user = User.objects.create_user(email="message@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Gamma", slug="gamma")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )
    lead = Lead.objects.create(
        organization=organization,
        full_name="Lead Message",
        created_by=user,
    )

    client = auth_client_for(user)
    response = client.post(
        "/api/v1/interactions/",
        {
            "lead_id": str(lead.id),
            "type": Interaction.Type.MESSAGE,
            "direction": Interaction.Direction.INTERNAL,
            "content": "Mensagem enviada no WhatsApp.",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "direction" in response.json()


@pytest.mark.django_db
def test_lead_and_deal_timeline_return_interactions_in_descending_order():
    user = User.objects.create_user(email="timeline@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Delta", slug="delta")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )
    lead = Lead.objects.create(
        organization=organization,
        full_name="Lead Timeline",
        created_by=user,
        assigned_to=user,
    )
    pipeline = Pipeline.objects.get(organization=organization, is_default=True)
    stage = pipeline.stages.filter(kind=Stage.Kind.OPEN).order_by("order").first()
    deal = Deal.objects.create(
        organization=organization,
        lead=lead,
        pipeline=pipeline,
        stage=stage,
        title="Deal Timeline",
        amount="1500.00",
        owner=user,
        created_by=user,
        position=0,
    )
    first_time = timezone.now() - timedelta(days=1)
    second_time = timezone.now()
    older = Interaction.objects.create(
        organization=organization,
        lead=lead,
        deal=deal,
        created_by=user,
        type=Interaction.Type.MESSAGE,
        direction=Interaction.Direction.OUTBOUND,
        content="Mensagem inicial",
        occurred_at=first_time,
    )
    newer = Interaction.objects.create(
        organization=organization,
        lead=lead,
        deal=deal,
        created_by=user,
        type=Interaction.Type.CALL,
        direction=Interaction.Direction.INBOUND,
        content="Retorno por telefone",
        occurred_at=second_time,
    )

    client = auth_client_for(user)
    lead_response = client.get(f"/api/v1/leads/{lead.id}/timeline/")
    deal_response = client.get(f"/api/v1/deals/{deal.id}/timeline/")

    assert lead_response.status_code == 200
    assert deal_response.status_code == 200
    lead_ids = [item["id"] for item in lead_response.json()["results"]]
    deal_ids = [item["id"] for item in deal_response.json()["results"]]
    assert lead_ids == [str(newer.id), str(older.id)]
    assert deal_ids == [str(newer.id), str(older.id)]


@pytest.mark.django_db
def test_delete_latest_interaction_recomputes_last_interaction():
    user = User.objects.create_user(email="delete@crm.com", password="StrongPass123")
    organization = Organization.objects.create(name="Epsilon", slug="epsilon")
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.MANAGER,
        is_default=True,
    )
    lead = Lead.objects.create(
        organization=organization,
        full_name="Lead Delete",
        created_by=user,
    )
    first_time = timezone.now() - timedelta(days=2)
    second_time = timezone.now() - timedelta(days=1)
    older = Interaction.objects.create(
        organization=organization,
        lead=lead,
        created_by=user,
        type=Interaction.Type.NOTE,
        direction=Interaction.Direction.INTERNAL,
        content="Anotação antiga",
        occurred_at=first_time,
    )
    latest = Interaction.objects.create(
        organization=organization,
        lead=lead,
        created_by=user,
        type=Interaction.Type.CALL,
        direction=Interaction.Direction.OUTBOUND,
        content="Ligação recente",
        occurred_at=second_time,
    )
    lead.last_interaction_at = second_time
    lead.save(update_fields=["last_interaction_at", "updated_at"])

    client = auth_client_for(user)
    response = client.delete(f"/api/v1/interactions/{latest.id}/")

    assert response.status_code == 204
    lead.refresh_from_db()
    assert lead.last_interaction_at == older.occurred_at


@pytest.mark.django_db
def test_sales_cannot_create_interaction_for_unrelated_lead():
    sales = User.objects.create_user(email="sales-interaction@crm.com", password="StrongPass123")
    manager = User.objects.create_user(email="manager-interaction@crm.com", password="StrongPass123")
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
        full_name="Lead Protegido",
        created_by=manager,
        assigned_to=manager,
    )

    client = auth_client_for(sales)
    response = client.post(
        "/api/v1/interactions/",
        {
            "lead_id": str(lead.id),
            "type": Interaction.Type.NOTE,
            "content": "Tentativa indevida",
        },
        format="json",
    )

    assert response.status_code == 400
