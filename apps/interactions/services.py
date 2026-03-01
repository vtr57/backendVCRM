from django.db.models import Q

from apps.interactions.models import Interaction
from apps.leads.models import Lead
from apps.pipeline.services import ensure_user_can_access_deal, ensure_user_can_access_lead


def sync_lead_last_interaction(lead: Lead) -> None:
    last_occurred_at = (
        Interaction.objects.filter(lead=lead, organization=lead.organization)
        .order_by("-occurred_at", "-created_at")
        .values_list("occurred_at", flat=True)
        .first()
    )
    lead.last_interaction_at = last_occurred_at
    lead.save(update_fields=["last_interaction_at", "updated_at"])


def filter_interactions_for_membership(queryset, request):
    membership = request.membership
    if membership.role == membership.Role.SALES:
        queryset = queryset.filter(
            Q(lead__created_by=request.user)
            | Q(lead__assigned_to=request.user)
            | Q(deal__owner=request.user)
            | Q(deal__created_by=request.user)
        )
    return queryset.distinct()


def validate_interaction_access(request, lead, deal=None):
    ensure_user_can_access_lead(request.membership, request.user, lead)
    if deal is not None:
        ensure_user_can_access_deal(request.membership, request.user, deal)
