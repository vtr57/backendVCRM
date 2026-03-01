from django_filters import rest_framework as filters

from apps.interactions.models import Interaction


class InteractionFilter(filters.FilterSet):
    lead_id = filters.UUIDFilter(field_name="lead_id")
    deal_id = filters.UUIDFilter(field_name="deal_id")
    type = filters.CharFilter(field_name="type")
    direction = filters.CharFilter(field_name="direction")
    occurred_from = filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="gte")
    occurred_to = filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="lte")

    class Meta:
        model = Interaction
        fields = ["lead_id", "deal_id", "type", "direction", "occurred_from", "occurred_to"]
