from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.interactions.models import Interaction
from apps.interactions.services import sync_lead_last_interaction, validate_interaction_access
from apps.leads.models import Lead
from apps.leads.serializers import LeadUserSerializer
from apps.pipeline.models import Deal


class InteractionSerializer(serializers.ModelSerializer):
    created_by = LeadUserSerializer(read_only=True)

    class Meta:
        model = Interaction
        fields = [
            "id",
            "lead",
            "deal",
            "type",
            "direction",
            "subject",
            "content",
            "outcome",
            "occurred_at",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]


class InteractionWriteSerializer(serializers.ModelSerializer):
    lead_id = serializers.UUIDField(write_only=True)
    deal_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = Interaction
        fields = [
            "id",
            "lead_id",
            "deal_id",
            "type",
            "direction",
            "subject",
            "content",
            "outcome",
            "occurred_at",
        ]
        read_only_fields = ["id"]

    def _organization(self):
        return self.context["request"].organization

    def _resolve_lead(self, lead_id):
        try:
            lead = Lead.objects.get(
                id=lead_id,
                organization=self._organization(),
                deleted_at__isnull=True,
            )
        except Lead.DoesNotExist as exc:
            raise serializers.ValidationError({"lead_id": "Lead not found."}) from exc
        return lead

    def _resolve_deal(self, deal_id):
        if deal_id is None:
            return None
        try:
            return Deal.objects.select_related("lead").get(
                id=deal_id,
                organization=self._organization(),
            )
        except Deal.DoesNotExist as exc:
            raise serializers.ValidationError({"deal_id": "Deal not found."}) from exc

    def validate(self, attrs):
        attrs = super().validate(attrs)
        lead_id = attrs.pop("lead_id", serializers.empty)
        deal_id = attrs.pop("deal_id", serializers.empty)

        if self.instance is None and lead_id is serializers.empty:
            raise serializers.ValidationError({"lead_id": "Lead is required."})

        if self.instance is None:
            lead = self._resolve_lead(lead_id)
            deal = self._resolve_deal(None if deal_id is serializers.empty else deal_id)
        else:
            lead = self.instance.lead if lead_id is serializers.empty else self._resolve_lead(lead_id)
            deal = self.instance.deal if deal_id is serializers.empty else self._resolve_deal(deal_id)

        if deal is not None and deal.lead_id != lead.id:
            raise serializers.ValidationError({"deal_id": "Deal must belong to the selected lead."})

        validate_interaction_access(self.context["request"], lead, deal)

        attrs["lead"] = lead
        attrs["deal"] = deal

        interaction_type = attrs.get("type", getattr(self.instance, "type", None))
        direction = attrs.get("direction", getattr(self.instance, "direction", Interaction.Direction.INTERNAL))

        if interaction_type == Interaction.Type.NOTE:
            attrs["direction"] = Interaction.Direction.INTERNAL
        elif interaction_type in {Interaction.Type.CALL, Interaction.Type.MESSAGE, Interaction.Type.EMAIL}:
            if direction == Interaction.Direction.INTERNAL:
                raise serializers.ValidationError(
                    {"direction": "Direction must be inbound or outbound for calls, messages or emails."}
                )

        if "occurred_at" not in attrs and self.instance is None:
            attrs["occurred_at"] = timezone.now()

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        interaction = Interaction.objects.create(
            organization=self._organization(),
            created_by=self.context["request"].user,
            **validated_data,
        )
        sync_lead_last_interaction(interaction.lead)
        return interaction

    @transaction.atomic
    def update(self, instance, validated_data):
        previous_lead = instance.lead

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        sync_lead_last_interaction(instance.lead)
        if previous_lead_id := getattr(previous_lead, "id", None):
            if previous_lead_id != instance.lead_id:
                sync_lead_last_interaction(previous_lead)
        return instance
