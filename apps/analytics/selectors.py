from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from apps.leads.models import Lead
from apps.pipeline.models import Deal, Pipeline, Stage, StageMovement
from apps.users.models import Membership

ZERO = Decimal("0.00")
ZERO_VALUE = Value(ZERO, output_field=DecimalField(max_digits=12, decimal_places=2))


def resolve_period_bounds(date_from=None, date_to=None):
    today = timezone.localdate()
    end_date = date_to or today
    start_date = date_from or end_date.replace(day=1)

    start_dt = timezone.make_aware(datetime.combine(start_date, time.min))
    end_dt = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min))
    return start_date, end_date, start_dt, end_dt


def scope_leads_queryset(queryset, membership, user):
    if membership.role == Membership.Role.SALES:
        queryset = queryset.filter(Q(created_by=user) | Q(assigned_to=user))
    return queryset.distinct()


def scope_deals_queryset(queryset, membership, user):
    if membership.role == Membership.Role.SALES:
        queryset = queryset.filter(
            Q(owner=user) | Q(created_by=user) | Q(lead__created_by=user) | Q(lead__assigned_to=user)
        )
    return queryset.distinct()


def scope_movements_queryset(queryset, membership, user):
    if membership.role == Membership.Role.SALES:
        queryset = queryset.filter(
            Q(deal__owner=user)
            | Q(deal__created_by=user)
            | Q(deal__lead__created_by=user)
            | Q(deal__lead__assigned_to=user)
        )
    return queryset.distinct()


def get_pipeline_for_analytics(organization, pipeline_id=None):
    if pipeline_id:
        return Pipeline.objects.filter(organization=organization, id=pipeline_id).first()
    return Pipeline.objects.filter(organization=organization, is_default=True, is_active=True).first()


def get_dashboard_metrics(*, organization, membership, user, date_from=None, date_to=None, pipeline_id=None):
    start_date, end_date, start_dt, end_dt = resolve_period_bounds(date_from, date_to)

    leads_queryset = scope_leads_queryset(
        Lead.objects.filter(organization=organization, deleted_at__isnull=True),
        membership,
        user,
    )
    deals_queryset = scope_deals_queryset(
        Deal.objects.filter(organization=organization).select_related("stage", "lead__source"),
        membership,
        user,
    )

    pipeline = get_pipeline_for_analytics(organization, pipeline_id)
    if pipeline is not None:
        deals_queryset = deals_queryset.filter(pipeline=pipeline)

    period_leads = leads_queryset.filter(created_at__gte=start_dt, created_at__lt=end_dt)
    period_deals = deals_queryset.filter(created_at__gte=start_dt, created_at__lt=end_dt)
    period_closed_deals = deals_queryset.filter(
        status=Deal.Status.WON,
        closed_at__gte=start_dt,
        closed_at__lt=end_dt,
    )
    open_deals = deals_queryset.filter(status=Deal.Status.OPEN)

    total_leads = period_leads.count()
    total_deals = period_deals.count()
    won_deals = period_closed_deals.count()
    closed_amount = period_closed_deals.aggregate(
        total=Coalesce(Sum("amount"), ZERO_VALUE)
    )["total"]
    open_pipeline_value = open_deals.aggregate(total=Coalesce(Sum("amount"), ZERO_VALUE))["total"]
    average_ticket = ZERO if won_deals == 0 else closed_amount / won_deals
    conversion_rate = 0 if total_deals == 0 else round((won_deals / total_deals) * 100, 2)

    leads_by_source = list(
        period_leads.values("source_id", "source__name")
        .annotate(lead_count=Count("id"))
        .order_by("-lead_count", "source__name")
    )
    for item in leads_by_source:
        item["source_name"] = item.pop("source__name")

    deals_by_stage = list(
        open_deals.values("stage_id", "stage__name", "stage__color", "stage__order")
        .annotate(
            deal_count=Count("id"),
            total_amount=Coalesce(Sum("amount"), ZERO_VALUE),
        )
        .order_by("stage__order", "stage__name")
    )
    for item in deals_by_stage:
        item["stage_name"] = item.pop("stage__name")
        item["stage_color"] = item.pop("stage__color")
        item["stage_order"] = item.pop("stage__order")

    won_amount_by_period = list(
        period_closed_deals.annotate(period=TruncDate("closed_at"))
        .values("period")
        .annotate(amount=Coalesce(Sum("amount"), ZERO_VALUE), won_count=Count("id"))
        .order_by("period")
    )

    return {
        "period": {"from": start_date, "to": end_date},
        "kpis": {
            "total_leads": total_leads,
            "total_deals": total_deals,
            "won_deals": won_deals,
            "conversion_rate": conversion_rate,
            "open_pipeline_value": open_pipeline_value,
            "closed_amount": closed_amount,
            "average_ticket": average_ticket,
        },
        "leads_by_source": leads_by_source,
        "deals_by_stage": deals_by_stage,
        "won_amount_by_period": won_amount_by_period,
        "pipeline": pipeline,
    }


def get_conversion_by_stage(*, organization, membership, user, date_from=None, date_to=None, pipeline_id=None):
    start_date, end_date, start_dt, end_dt = resolve_period_bounds(date_from, date_to)
    pipeline = get_pipeline_for_analytics(organization, pipeline_id)
    if pipeline is None:
        return {"period": {"from": start_date, "to": end_date}, "pipeline": None, "results": []}

    stages = list(pipeline.stages.order_by("order"))
    deals_queryset = scope_deals_queryset(Deal.objects.filter(organization=organization, pipeline=pipeline), membership, user)
    movement_queryset = scope_movements_queryset(
        StageMovement.objects.filter(
            organization=organization,
            to_stage__pipeline=pipeline,
            moved_at__gte=start_dt,
            moved_at__lt=end_dt,
        ),
        membership,
        user,
    )

    current_stage_metrics = {
        item["stage_id"]: item
        for item in deals_queryset.values("stage_id").annotate(
            current_deals=Count("id"),
            current_amount=Coalesce(Sum("amount"), ZERO_VALUE),
        )
    }
    entered_metrics = {
        item["to_stage_id"]: item
        for item in movement_queryset.values("to_stage_id").annotate(
            entered_deals=Count("deal_id", distinct=True),
            won_deals=Count("deal_id", distinct=True, filter=Q(deal__status=Deal.Status.WON)),
        )
    }

    results = []
    for stage in stages:
        current = current_stage_metrics.get(stage.id, {})
        entered = entered_metrics.get(stage.id, {})
        entered_deals = entered.get("entered_deals", 0)
        won_deals = entered.get("won_deals", 0)
        conversion_rate = 0 if entered_deals == 0 else round((won_deals / entered_deals) * 100, 2)
        results.append(
            {
                "stage_id": stage.id,
                "stage_name": stage.name,
                "stage_kind": stage.kind,
                "stage_color": stage.color,
                "entered_deals": entered_deals,
                "won_deals": won_deals,
                "conversion_rate": conversion_rate,
                "current_deals": current.get("current_deals", 0),
                "current_amount": current.get("current_amount", ZERO),
            }
        )

    return {
        "period": {"from": start_date, "to": end_date},
        "pipeline": pipeline,
        "results": results,
    }


def get_conversion_by_owner(*, organization, membership, user, date_from=None, date_to=None, pipeline_id=None):
    start_date, end_date, start_dt, end_dt = resolve_period_bounds(date_from, date_to)
    deals_queryset = scope_deals_queryset(Deal.objects.filter(organization=organization), membership, user)
    if pipeline_id:
        deals_queryset = deals_queryset.filter(pipeline_id=pipeline_id)
    period_deals = deals_queryset.filter(created_at__gte=start_dt, created_at__lt=end_dt)

    results = list(
        period_deals.values("owner_id", "owner__first_name", "owner__last_name", "owner__email")
        .annotate(
            total_deals=Count("id"),
            open_deals=Count("id", filter=Q(status=Deal.Status.OPEN)),
            won_deals=Count("id", filter=Q(status=Deal.Status.WON)),
            lost_deals=Count("id", filter=Q(status=Deal.Status.LOST)),
            won_amount=Coalesce(
                Sum("amount", filter=Q(status=Deal.Status.WON, closed_at__gte=start_dt, closed_at__lt=end_dt)),
                ZERO_VALUE,
            ),
            open_amount=Coalesce(Sum("amount", filter=Q(status=Deal.Status.OPEN)), ZERO_VALUE),
        )
        .order_by("-won_amount", "-total_deals")
    )

    for item in results:
        owner_first_name = item.pop("owner__first_name")
        owner_last_name = item.pop("owner__last_name")
        owner_email = item.pop("owner__email")
        item["owner_name"] = (
            f"{owner_first_name or ''} {owner_last_name or ''}".strip() or owner_email or "Sem responsavel"
        )
        item["conversion_rate"] = (
            0 if item["total_deals"] == 0 else round((item["won_deals"] / item["total_deals"]) * 100, 2)
        )
        item["owner_email"] = owner_email

    return {"period": {"from": start_date, "to": end_date}, "results": results}


def get_source_profitability(*, organization, membership, user, date_from=None, date_to=None, pipeline_id=None):
    start_date, end_date, start_dt, end_dt = resolve_period_bounds(date_from, date_to)
    deals_queryset = scope_deals_queryset(
        Deal.objects.filter(organization=organization).select_related("lead__source"),
        membership,
        user,
    )
    leads_queryset = scope_leads_queryset(
        Lead.objects.filter(organization=organization, deleted_at__isnull=True),
        membership,
        user,
    )
    if pipeline_id:
        deals_queryset = deals_queryset.filter(pipeline_id=pipeline_id)
    period_deals = deals_queryset.filter(created_at__gte=start_dt, created_at__lt=end_dt)
    period_leads = leads_queryset.filter(created_at__gte=start_dt, created_at__lt=end_dt)

    lead_metrics = {
        item["source_id"]: item
        for item in period_leads.values("source_id", "source__name").annotate(total_leads=Count("id"))
    }
    deal_metrics = list(
        period_deals.values("lead__source_id", "lead__source__name")
        .annotate(
            total_deals=Count("id"),
            won_deals=Count("id", filter=Q(status=Deal.Status.WON)),
            won_amount=Coalesce(
                Sum("amount", filter=Q(status=Deal.Status.WON, closed_at__gte=start_dt, closed_at__lt=end_dt)),
                ZERO_VALUE,
            ),
            open_amount=Coalesce(Sum("amount", filter=Q(status=Deal.Status.OPEN)), ZERO_VALUE),
        )
        .order_by("-won_amount", "-total_deals")
    )

    results = []
    seen = set()
    for item in deal_metrics:
        source_id = item["lead__source_id"]
        seen.add(source_id)
        lead_data = lead_metrics.get(source_id, {})
        total_deals = item["total_deals"]
        won_deals = item["won_deals"]
        results.append(
            {
                "source_id": source_id,
                "source_name": item["lead__source__name"] or "Sem origem",
                "total_leads": lead_data.get("total_leads", 0),
                "total_deals": total_deals,
                "won_deals": won_deals,
                "won_amount": item["won_amount"],
                "open_amount": item["open_amount"],
                "conversion_rate": 0 if total_deals == 0 else round((won_deals / total_deals) * 100, 2),
            }
        )

    for source_id, item in lead_metrics.items():
        if source_id in seen:
            continue
        results.append(
            {
                "source_id": source_id,
                "source_name": item["source__name"] or "Sem origem",
                "total_leads": item["total_leads"],
                "total_deals": 0,
                "won_deals": 0,
                "won_amount": ZERO,
                "open_amount": ZERO,
                "conversion_rate": 0,
            }
        )

    results.sort(key=lambda item: (-item["won_amount"], -item["total_deals"], item["source_name"]))
    return {"period": {"from": start_date, "to": end_date}, "results": results}
