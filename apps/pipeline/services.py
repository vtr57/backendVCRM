from django.db import transaction
from django.db.models import F, Max, Q
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.leads.models import Lead
from apps.pipeline.models import Deal, Pipeline, Stage, StageMovement
from apps.users.models import Membership, Organization, User

DEFAULT_PIPELINE_NAME = "Pipeline Principal"
DEFAULT_STAGE_BLUEPRINT = [
    {"name": "Entrada", "slug": "entrada", "order": 1, "color": "#BC5C2D", "probability": 10, "kind": Stage.Kind.OPEN},
    {"name": "Contato", "slug": "contato", "order": 2, "color": "#D77A3F", "probability": 30, "kind": Stage.Kind.OPEN},
    {"name": "Qualificação", "slug": "qualificacao", "order": 3, "color": "#E39B49", "probability": 55, "kind": Stage.Kind.OPEN},
    {"name": "Proposta", "slug": "proposta", "order": 4, "color": "#6D9F71", "probability": 80, "kind": Stage.Kind.OPEN},
    {"name": "Fechado", "slug": "fechado", "order": 5, "color": "#2C8B57", "probability": 100, "kind": Stage.Kind.WON},
    {"name": "Perdido", "slug": "perdido", "order": 6, "color": "#A84A44", "probability": 0, "kind": Stage.Kind.LOST},
]


def seed_pipeline_stages(pipeline: Pipeline) -> None:
    if pipeline.stages.exists():
        return

    Stage.objects.bulk_create([Stage(pipeline=pipeline, **stage_data) for stage_data in DEFAULT_STAGE_BLUEPRINT])


def create_default_pipeline_for_organization(organization: Organization) -> Pipeline:
    pipeline = organization.pipelines.filter(is_default=True).first()
    if pipeline is not None:
        return pipeline

    with transaction.atomic():
        pipeline = Pipeline.objects.create(
            organization=organization,
            name=DEFAULT_PIPELINE_NAME,
            is_default=True,
        )
        seed_pipeline_stages(pipeline)
        return pipeline


def get_default_pipeline_for_organization(organization: Organization) -> Pipeline:
    pipeline = organization.pipelines.filter(is_default=True, is_active=True).first()
    if pipeline is None:
        pipeline = create_default_pipeline_for_organization(organization)
    return pipeline


def get_first_open_stage(pipeline: Pipeline) -> Stage:
    stage = pipeline.stages.filter(kind=Stage.Kind.OPEN).order_by("order").first()
    if stage is None:
        raise ValidationError("This pipeline does not have an open stage configured.")
    return stage


def get_next_position(stage: Stage) -> int:
    current = stage.deals.aggregate(max_position=Max("position"))["max_position"]
    if current is None:
        return 0
    return current + 1


def build_individual_deal_scope(user: User) -> Q:
    return Q(owner=user) | Q(created_by=user) | Q(lead__created_by=user) | Q(lead__assigned_to=user)


def resolve_board_member_user(
    *,
    organization: Organization,
    membership: Membership,
    request_user: User,
    member_user_id: str | None = None,
) -> User:
    if membership.role == Membership.Role.SALES:
        return request_user

    if not member_user_id:
        return request_user

    try:
        member_user = User.objects.get(id=member_user_id, is_active=True)
    except User.DoesNotExist as exc:
        raise ValidationError({"member_user_id": "Team member not found."}) from exc

    has_membership = Membership.objects.filter(
        organization=organization,
        user=member_user,
        is_active=True,
    ).exists()
    if not has_membership:
        raise ValidationError({"member_user_id": "Team member does not belong to this organization."})

    return member_user


def record_initial_stage_movement(deal: Deal) -> None:
    StageMovement.objects.create(
        organization=deal.organization,
        deal=deal,
        from_stage=None,
        to_stage=deal.stage,
        moved_by=deal.created_by,
        from_position=0,
        to_position=deal.position,
        note="Deal created",
    )


def sync_lead_status_from_stage(lead: Lead, stage: Stage) -> None:
    if stage.kind == Stage.Kind.WON:
        lead.status = Lead.Status.WON
    elif stage.kind == Stage.Kind.LOST:
        lead.status = Lead.Status.LOST
    else:
        open_stages = list(stage.pipeline.stages.filter(kind=Stage.Kind.OPEN).order_by("order"))
        stage_index = next((index for index, item in enumerate(open_stages) if item.id == stage.id), 0)
        if stage_index <= 0:
            lead.status = Lead.Status.NEW
        elif stage_index == 1:
            lead.status = Lead.Status.CONTACTED
        elif stage.probability >= 70:
            lead.status = Lead.Status.PROPOSAL
        else:
            lead.status = Lead.Status.QUALIFIED
    lead.save(update_fields=["status", "updated_at"])


def ensure_user_can_access_deal(membership: Membership, user: User, deal: Deal) -> None:
    if membership.role in {
        Membership.Role.OWNER,
        Membership.Role.ADMIN,
        Membership.Role.MANAGER,
    }:
        return

    if membership.role == Membership.Role.SALES and (
        deal.created_by_id == user.id
        or deal.owner_id == user.id
        or deal.lead.created_by_id == user.id
        or deal.lead.assigned_to_id == user.id
    ):
        return

    raise ValidationError("You do not have permission to access this deal.")


def ensure_user_can_access_lead(membership: Membership, user: User, lead: Lead) -> None:
    if membership.role in {
        Membership.Role.OWNER,
        Membership.Role.ADMIN,
        Membership.Role.MANAGER,
    }:
        return

    if membership.role == Membership.Role.SALES and (
        lead.created_by_id == user.id or lead.assigned_to_id == user.id
    ):
        return

    raise ValidationError("You do not have permission to use this lead.")


@transaction.atomic
def move_deal(
    *,
    deal: Deal,
    target_stage: Stage,
    moved_by: User,
    target_position: int | None = None,
    note: str = "",
    lost_reason: str = "",
) -> Deal:
    deal = (
        Deal.objects.select_for_update()
        .select_related("stage", "pipeline", "lead")
        .get(id=deal.id)
    )
    old_stage = deal.stage
    old_position = deal.position

    if target_stage.pipeline_id != deal.pipeline_id:
        raise ValidationError("Target stage must belong to the same pipeline.")

    if target_stage.kind == Stage.Kind.LOST and not (lost_reason or deal.lost_reason):
        raise ValidationError({"lost_reason": "Lost reason is required when moving to a lost stage."})

    if target_position is None:
        target_position = get_next_position(target_stage)

    target_position = max(target_position, 0)

    Deal.objects.filter(stage=old_stage, position__gt=old_position).update(position=F("position") - 1)
    target_stage_count = Deal.objects.filter(stage=target_stage).exclude(id=deal.id).count()
    target_position = min(target_position, target_stage_count)

    Deal.objects.filter(stage=target_stage, position__gte=target_position).exclude(id=deal.id).update(
        position=F("position") + 1
    )

    deal.stage = target_stage
    deal.position = target_position
    if target_stage.kind == Stage.Kind.LOST:
        deal.lost_reason = lost_reason or deal.lost_reason
    deal.sync_status_from_stage()
    deal.save(
        update_fields=[
            "stage",
            "position",
            "status",
            "closed_at",
            "lost_reason",
            "updated_at",
        ]
    )

    sync_lead_status_from_stage(deal.lead, target_stage)

    StageMovement.objects.create(
        organization=deal.organization,
        deal=deal,
        from_stage=old_stage,
        to_stage=target_stage,
        moved_by=moved_by,
        from_position=old_position,
        to_position=target_position,
        note=note,
    )
    return deal
