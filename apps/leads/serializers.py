from django.db import transaction
from rest_framework import serializers

from apps.leads.models import Lead, LeadSource, Tag
from apps.users.models import Membership, User


class LeadSourceSerializer(serializers.ModelSerializer):
    def validate_name(self, value):
        request = self.context.get("request")
        organization = getattr(request, "organization", None)
        if organization is None:
            return value

        queryset = LeadSource.objects.filter(organization=organization, name__iexact=value)
        if self.instance is not None:
            queryset = queryset.exclude(id=self.instance.id)
        if queryset.exists():
            raise serializers.ValidationError("A lead source with this name already exists.")
        return value

    class Meta:
        model = LeadSource
        fields = ["id", "name", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class TagSerializer(serializers.ModelSerializer):
    def validate_name(self, value):
        request = self.context.get("request")
        organization = getattr(request, "organization", None)
        if organization is None:
            return value

        queryset = Tag.objects.filter(organization=organization, name__iexact=value)
        if self.instance is not None:
            queryset = queryset.exclude(id=self.instance.id)
        if queryset.exists():
            raise serializers.ValidationError("A tag with this name already exists.")
        return value

    class Meta:
        model = Tag
        fields = ["id", "name", "color", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class LeadUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "full_name"]


class LeadListSerializer(serializers.ModelSerializer):
    source = LeadSourceSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    assigned_to = LeadUserSerializer(read_only=True)
    created_by = LeadUserSerializer(read_only=True)

    class Meta:
        model = Lead
        fields = [
            "id",
            "full_name",
            "email",
            "phone",
            "company_name",
            "job_title",
            "status",
            "temperature",
            "estimated_value",
            "notes_summary",
            "last_interaction_at",
            "next_action_at",
            "source",
            "tags",
            "assigned_to",
            "created_by",
            "created_at",
            "updated_at",
        ]


class LeadDetailSerializer(LeadListSerializer):
    class Meta(LeadListSerializer.Meta):
        fields = LeadListSerializer.Meta.fields


class LeadWriteSerializer(serializers.ModelSerializer):
    source_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)
    tag_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        write_only=True,
    )
    assigned_to_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = Lead
        fields = [
            "id",
            "full_name",
            "email",
            "phone",
            "company_name",
            "job_title",
            "status",
            "temperature",
            "estimated_value",
            "notes_summary",
            "last_interaction_at",
            "next_action_at",
            "source_id",
            "tag_ids",
            "assigned_to_id",
        ]
        read_only_fields = ["id"]

    def _get_organization(self):
        request = self.context["request"]
        return request.organization

    def _resolve_source(self, source_id):
        if source_id is None:
            return None

        organization = self._get_organization()
        try:
            return LeadSource.objects.get(id=source_id, organization=organization)
        except LeadSource.DoesNotExist as exc:
            raise serializers.ValidationError({"source_id": "Lead source not found."}) from exc

    def _resolve_tags(self, tag_ids):
        if tag_ids is None:
            return None

        organization = self._get_organization()
        tags = list(Tag.objects.filter(id__in=tag_ids, organization=organization))
        if len(tags) != len(set(tag_ids)):
            raise serializers.ValidationError({"tag_ids": "One or more tags are invalid."})
        return tags

    def _resolve_assigned_to(self, assigned_to_id):
        if assigned_to_id is None:
            return None

        organization = self._get_organization()
        try:
            user = User.objects.get(id=assigned_to_id, is_active=True)
        except User.DoesNotExist as exc:
            raise serializers.ValidationError({"assigned_to_id": "Assignee not found."}) from exc

        has_membership = Membership.objects.filter(
            user=user,
            organization=organization,
            is_active=True,
        ).exists()
        if not has_membership:
            raise serializers.ValidationError(
                {"assigned_to_id": "Assignee does not belong to this organization."}
            )
        return user

    def validate(self, attrs):
        attrs = super().validate(attrs)
        source_id = attrs.pop("source_id", serializers.empty)
        tag_ids = attrs.pop("tag_ids", serializers.empty)
        assigned_to_id = attrs.pop("assigned_to_id", serializers.empty)

        if source_id is not serializers.empty:
            attrs["source"] = self._resolve_source(source_id)
        if tag_ids is not serializers.empty:
            attrs["_tags"] = self._resolve_tags(tag_ids)
        if assigned_to_id is not serializers.empty:
            attrs["assigned_to"] = self._resolve_assigned_to(assigned_to_id)

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        tags = validated_data.pop("_tags", [])
        request = self.context["request"]
        lead = Lead.objects.create(
            organization=request.organization,
            created_by=request.user,
            **validated_data,
        )
        if tags:
            lead.tags.set(tags)
        return lead

    @transaction.atomic
    def update(self, instance, validated_data):
        tags = validated_data.pop("_tags", serializers.empty)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if tags is not serializers.empty:
            instance.tags.set(tags)
        return instance
