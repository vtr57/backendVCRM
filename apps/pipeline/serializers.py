from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers

from apps.leads.models import Lead
from apps.leads.serializers import LeadListSerializer, LeadUserSerializer
from apps.pipeline.models import Deal, Pipeline, Stage, StageMovement
from apps.pipeline.services import (
    ensure_user_can_access_lead,
    get_default_pipeline_for_organization,
    get_first_open_stage,
    get_next_position,
    record_initial_stage_movement,
    sync_lead_status_from_stage,
)
from apps.users.models import Membership, User


class PipelineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pipeline
        fields = ["id", "name", "is_default", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value):
        request = self.context.get("request")
        organization = getattr(request, "organization", None)
        if organization is None:
            return value

        queryset = Pipeline.objects.filter(organization=organization, name__iexact=value)
        if self.instance is not None:
            queryset = queryset.exclude(id=self.instance.id)
        if queryset.exists():
            raise serializers.ValidationError("A pipeline with this name already exists.")
        return value


class StageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stage
        fields = [
            "id",
            "pipeline",
            "name",
            "slug",
            "order",
            "color",
            "probability",
            "kind",
            "wip_limit",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "pipeline"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        name = attrs.get("name", getattr(self.instance, "name", ""))
        slug = attrs.get("slug") or slugify(name)
        if not slug:
            raise serializers.ValidationError({"slug": "Stage slug is invalid."})
        attrs["slug"] = slug
        return attrs


class DealListSerializer(serializers.ModelSerializer):
    lead = LeadListSerializer(read_only=True)
    owner = LeadUserSerializer(read_only=True)
    created_by = LeadUserSerializer(read_only=True)

    class Meta:
        model = Deal
        fields = [
            "id",
            "title",
            "amount",
            "status",
            "position",
            "expected_close_date",
            "closed_at",
            "lost_reason",
            "lead",
            "owner",
            "created_by",
            "created_at",
            "updated_at",
        ]


class DealDetailSerializer(DealListSerializer):
    stage = StageSerializer(read_only=True)
    pipeline = PipelineSerializer(read_only=True)

    class Meta(DealListSerializer.Meta):
        fields = DealListSerializer.Meta.fields + ["stage", "pipeline"]


class DealWriteSerializer(serializers.ModelSerializer):
    lead_id = serializers.UUIDField(write_only=True)
    pipeline_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)
    stage_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)
    owner_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = Deal
        fields = [
            "id",
            "title",
            "amount",
            "expected_close_date",
            "lost_reason",
            "lead_id",
            "pipeline_id",
            "stage_id",
            "owner_id",
        ]
        read_only_fields = ["id"]

    def _organization(self):
        return self.context["request"].organization

    def _membership(self):
        return self.context["request"].membership

    def _resolve_lead(self, lead_id):
        organization = self._organization()
        try:
            lead = Lead.objects.get(id=lead_id, organization=organization, deleted_at__isnull=True)
        except Lead.DoesNotExist as exc:
            raise serializers.ValidationError({"lead_id": "Lead not found."}) from exc
        ensure_user_can_access_lead(self._membership(), self.context["request"].user, lead)
        return lead

    def _resolve_pipeline(self, pipeline_id):
        organization = self._organization()
        if pipeline_id is None:
            return get_default_pipeline_for_organization(organization)
        try:
            return Pipeline.objects.get(id=pipeline_id, organization=organization, is_active=True)
        except Pipeline.DoesNotExist as exc:
            raise serializers.ValidationError({"pipeline_id": "Pipeline not found."}) from exc

    def _resolve_stage(self, stage_id, pipeline):
        if stage_id is None:
            return get_first_open_stage(pipeline)
        try:
            return Stage.objects.get(id=stage_id, pipeline=pipeline)
        except Stage.DoesNotExist as exc:
            raise serializers.ValidationError({"stage_id": "Stage not found in this pipeline."}) from exc

    def _resolve_owner(self, owner_id):
        if owner_id is None:
            return None

        organization = self._organization()
        try:
            owner = User.objects.get(id=owner_id, is_active=True)
        except User.DoesNotExist as exc:
            raise serializers.ValidationError({"owner_id": "Owner not found."}) from exc

        has_membership = Membership.objects.filter(
            user=owner,
            organization=organization,
            is_active=True,
        ).exists()
        if not has_membership:
            raise serializers.ValidationError({"owner_id": "Owner does not belong to this organization."})
        return owner

    def validate(self, attrs):
        attrs = super().validate(attrs)
        lead_id = attrs.pop("lead_id", serializers.empty)
        pipeline_id = attrs.pop("pipeline_id", serializers.empty)
        stage_id = attrs.pop("stage_id", serializers.empty)
        owner_id = attrs.pop("owner_id", serializers.empty)

        if self.instance is None:
            lead = self._resolve_lead(lead_id)
            pipeline = self._resolve_pipeline(None if pipeline_id is serializers.empty else pipeline_id)
            stage = self._resolve_stage(None if stage_id is serializers.empty else stage_id, pipeline)
            owner = self._resolve_owner(None if owner_id is serializers.empty else owner_id)

            if stage.kind == Stage.Kind.LOST and not attrs.get("lost_reason"):
                raise serializers.ValidationError(
                    {"lost_reason": "Lost reason is required when creating a deal in a lost stage."}
                )

            attrs["lead"] = lead
            attrs["pipeline"] = pipeline
            attrs["stage"] = stage
            attrs["owner"] = owner or lead.assigned_to or self.context["request"].user
            return attrs

        if lead_id is not serializers.empty and str(self.instance.lead_id) != str(lead_id):
            raise serializers.ValidationError({"lead_id": "Lead cannot be changed after deal creation."})

        if pipeline_id is not serializers.empty and str(self.instance.pipeline_id) != str(pipeline_id):
            raise serializers.ValidationError(
                {"pipeline_id": "Use the move endpoint to change pipeline placement."}
            )

        if stage_id is not serializers.empty and str(self.instance.stage_id) != str(stage_id):
            raise serializers.ValidationError({"stage_id": "Use the move endpoint to change stage."})

        if owner_id is not serializers.empty:
            attrs["owner"] = self._resolve_owner(owner_id)

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        stage = validated_data["stage"]
        deal = Deal(
            organization=self._organization(),
            created_by=self.context["request"].user,
            position=get_next_position(stage),
            **validated_data,
        )
        deal.sync_status_from_stage()
        deal.save()
        record_initial_stage_movement(deal)
        sync_lead_status_from_stage(deal.lead, stage)
        return deal

    @transaction.atomic
    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.sync_status_from_stage()
        instance.save()
        return instance


class StageMovementSerializer(serializers.ModelSerializer):
    from_stage = StageSerializer(read_only=True)
    to_stage = StageSerializer(read_only=True)
    moved_by = LeadUserSerializer(read_only=True)

    class Meta:
        model = StageMovement
        fields = [
            "id",
            "from_stage",
            "to_stage",
            "moved_by",
            "moved_at",
            "from_position",
            "to_position",
            "note",
        ]


class DealMoveSerializer(serializers.Serializer):
    stage_id = serializers.UUIDField()
    position = serializers.IntegerField(required=False, min_value=0)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)
    lost_reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class BoardDealSerializer(serializers.ModelSerializer):
    lead = serializers.SerializerMethodField()
    owner = LeadUserSerializer(read_only=True)

    class Meta:
        model = Deal
        fields = [
            "id",
            "title",
            "amount",
            "status",
            "position",
            "expected_close_date",
            "closed_at",
            "lead",
            "owner",
        ]

    def get_lead(self, obj):
        return {
            "id": str(obj.lead_id),
            "full_name": obj.lead.full_name,
            "company_name": obj.lead.company_name,
            "email": obj.lead.email,
            "phone": obj.lead.phone,
            "status": obj.lead.status,
        }


class BoardStageSerializer(serializers.ModelSerializer):
    deals = serializers.SerializerMethodField()

    class Meta:
        model = Stage
        fields = [
            "id",
            "name",
            "slug",
            "order",
            "color",
            "probability",
            "kind",
            "wip_limit",
            "deals",
        ]

    def get_deals(self, obj):
        deal_map = self.context["deal_map"]
        deals = deal_map.get(obj.id, [])
        return BoardDealSerializer(deals, many=True).data


class BoardSerializer(serializers.Serializer):
    pipeline = PipelineSerializer()
    stages = serializers.ListField()
