from apps.analytics.selectors import (
    get_conversion_by_owner,
    get_conversion_by_stage,
    get_dashboard_metrics,
    get_source_profitability,
)


def build_dashboard_data(**kwargs):
    return get_dashboard_metrics(**kwargs)


def build_conversion_by_stage_report(**kwargs):
    return get_conversion_by_stage(**kwargs)


def build_conversion_by_owner_report(**kwargs):
    return get_conversion_by_owner(**kwargs)


def build_source_profitability_report(**kwargs):
    return get_source_profitability(**kwargs)
