from django.db.models import Q
from django_filters import rest_framework as filters

from apps.leads.models import Lead


class LeadFilter(filters.FilterSet):
    search = filters.CharFilter(method="filter_search")
    status = filters.CharFilter(field_name="status")
    source = filters.UUIDFilter(field_name="source_id")
    assigned_to = filters.UUIDFilter(field_name="assigned_to_id")
    tags = filters.CharFilter(method="filter_tags")
    created_from = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_to = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Lead
        fields = [
            "status",
            "source",
            "assigned_to",
            "created_from",
            "created_to",
        ]

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(full_name__icontains=value)
            | Q(email__icontains=value)
            | Q(phone__icontains=value)
            | Q(company_name__icontains=value)
        )

    def filter_tags(self, queryset, name, value):
        if not value:
            return queryset
        tag_names = [tag.strip() for tag in value.split(",") if tag.strip()]
        if not tag_names:
            return queryset
        return queryset.filter(tags__name__in=tag_names).distinct()
