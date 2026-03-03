import csv
import io
import json
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters as drf_filters
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.interactions.serializers import InteractionSerializer
from apps.interactions.services import filter_interactions_for_membership
from apps.leads.decimal_utils import normalize_decimal_input
from apps.leads.filters import LeadFilter
from apps.leads.models import Lead, LeadSource, Tag
from apps.leads.pagination import LeadPagination
from apps.leads.permissions import LeadAccessPermission, LeadConfigurationPermission
from apps.leads.serializers import (
    LeadBulkDeleteSerializer,
    LeadDetailSerializer,
    LeadListSerializer,
    LeadSourceSerializer,
    LeadWriteSerializer,
    TagSerializer,
)
from apps.users.models import Membership

IMPORTABLE_LEAD_FIELDS = [
    "organization",
    "full_name",
    "email",
    "phone",
    "job_title",
    "source",
    "estimated_value",
]


class OrganizationScopedBaseViewSet(viewsets.ModelViewSet):
    def get_organization(self):
        return self.request.organization


class LeadViewSet(OrganizationScopedBaseViewSet):
    permission_classes = [LeadAccessPermission]
    pagination_class = LeadPagination
    filter_backends = [DjangoFilterBackend, drf_filters.OrderingFilter]
    filterset_class = LeadFilter
    ordering_fields = ["created_at", "updated_at", "estimated_value", "full_name", "next_action_at"]
    ordering = ["-created_at"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        queryset = (
            Lead.objects.filter(
                organization=self.get_organization(),
                deleted_at__isnull=True,
            )
            .select_related("source", "assigned_to", "created_by")
            .prefetch_related("tags")
        )

        membership = self.request.membership
        if membership.role == Membership.Role.SALES:
            queryset = queryset.filter(
                Q(created_by=self.request.user) | Q(assigned_to=self.request.user)
            )

        return queryset.distinct().order_by(*self.ordering)

    def get_serializer_class(self):
        if self.action == "bulk_delete":
            return LeadBulkDeleteSerializer
        if self.action in {"list"}:
            return LeadListSerializer
        if self.action in {"retrieve"}:
            return LeadDetailSerializer
        return LeadWriteSerializer

    def perform_destroy(self, instance):
        instance.soft_delete()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        lead = Lead.objects.select_related("source", "assigned_to", "created_by").prefetch_related(
            "tags"
        ).get(id=serializer.instance.id)
        output = LeadDetailSerializer(lead, context=self.get_serializer_context())
        headers = self.get_success_headers(output.data)
        return Response(output.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        instance.refresh_from_db()
        output = LeadDetailSerializer(instance, context=self.get_serializer_context())
        return Response(output.data)

    @action(detail=False, methods=["post"])
    @transaction.atomic
    def bulk_delete(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": "Selecione ao menos um lead valido para excluir."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        lead_ids = list(dict.fromkeys(str(lead_id) for lead_id in serializer.validated_data["lead_ids"]))
        leads = list(self.get_queryset().filter(id__in=lead_ids))

        if len(leads) != len(lead_ids):
            return Response(
                {"detail": "Um ou mais leads selecionados nao estao disponiveis para exclusao."},
                status=status.HTTP_404_NOT_FOUND,
            )

        for lead in leads:
            lead.soft_delete()

        return Response({"deleted_count": len(leads)}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def export(self, request):
        queryset = self.get_queryset().order_by("-created_at")

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="leads-export.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "id",
                "organization",
                "assigned_to",
                "created_by",
                "full_name",
                "email",
                "phone",
                "company_name",
                "job_title",
                "source",
                "tags",
                "status",
                "temperature",
                "estimated_value",
                "notes_summary",
                "last_interaction_at",
                "next_action_at",
                "created_at",
                "updated_at",
                "deleted_at",
            ]
        )

        for lead in queryset:
            writer.writerow(
                [
                    str(lead.id),
                    str(lead.organization_id),
                    str(lead.assigned_to_id or ""),
                    str(lead.created_by_id),
                    lead.full_name,
                    lead.email,
                    lead.phone,
                    lead.company_name,
                    lead.job_title,
                    str(lead.source_id or ""),
                    ",".join(str(tag.id) for tag in lead.tags.all()),
                    lead.status,
                    lead.temperature,
                    str(lead.estimated_value),
                    lead.notes_summary,
                    lead.last_interaction_at.isoformat() if lead.last_interaction_at else "",
                    lead.next_action_at.isoformat() if lead.next_action_at else "",
                    lead.created_at.isoformat() if lead.created_at else "",
                    lead.updated_at.isoformat() if lead.updated_at else "",
                    lead.deleted_at.isoformat() if lead.deleted_at else "",
                ]
            )

        return response

    @action(detail=False, methods=["post"])
    def import_csv(self, request):
        file = request.FILES.get("file")
        mapping_raw = request.data.get("mapping")

        if file is None:
            return Response({"detail": "CSV file is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not mapping_raw:
            return Response({"detail": "Field mapping is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            mapping = json.loads(mapping_raw)
        except json.JSONDecodeError:
            return Response({"detail": "Field mapping must be valid JSON."}, status=status.HTTP_400_BAD_REQUEST)

        mapping = {field: mapping.get(field, "") for field in IMPORTABLE_LEAD_FIELDS}

        try:
            decoded = file.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            return Response({"detail": "CSV file must be UTF-8 encoded."}, status=status.HTTP_400_BAD_REQUEST)

        reader = csv.DictReader(
            io.StringIO(decoded),
            delimiter=self._detect_csv_delimiter(decoded),
        )
        if reader.fieldnames is None:
            return Response({"detail": "CSV header row is missing."}, status=status.HTTP_400_BAD_REQUEST)

        imported_count = 0
        errors = []

        for row_index, row in enumerate(reader, start=2):
            if self._should_skip_import_row(row):
                continue
            try:
                self._import_csv_row(request, row, mapping)
                imported_count += 1
            except Exception as exc:
                errors.append({"row": row_index, "error": str(exc)})

        return Response(
            {
                "imported_count": imported_count,
                "error_count": len(errors),
                "errors": errors,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"])
    def timeline(self, request, pk=None):
        lead = self.get_object()
        queryset = filter_interactions_for_membership(
            lead.interactions.select_related("deal", "created_by").all(),
            request,
        )
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = InteractionSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = InteractionSerializer(queryset, many=True)
        return Response(serializer.data)

    def _import_csv_row(self, request, row, mapping):
        def mapped_value(field_name):
            column = mapping.get(field_name)
            if not column:
                return ""
            return (row.get(column) or "").strip()

        def parse_decimal_value(value, field_name):
            if not value:
                return Decimal("0")

            try:
                return Decimal(normalize_decimal_input(value))
            except InvalidOperation as exc:
                raise ValueError(f"{field_name} must be a valid decimal value.") from exc

        def resolve_source(value):
            if not value:
                return None

            source = LeadSource.objects.filter(
                organization=request.organization,
                name__iexact=value,
            ).first()
            if source is not None:
                return source

            source = LeadSource.objects.create(
                organization=request.organization,
                name=value,
            )
            return source

        full_name = mapped_value("full_name")
        if not full_name:
            raise ValueError("full_name is required.")

        source = resolve_source(mapped_value("source"))
        estimated_value = parse_decimal_value(
            mapped_value("estimated_value"),
            "estimated_value",
        )

        Lead.objects.create(
            organization=request.organization,
            created_by=request.user,
            full_name=full_name,
            email=mapped_value("email"),
            phone=mapped_value("phone"),
            job_title=mapped_value("job_title"),
            source=source,
            status=Lead.Status.NEW,
            temperature=Lead.Temperature.COLD,
            estimated_value=estimated_value,
            notes_summary="",
        )

    def _detect_csv_delimiter(self, content):
        first_non_empty_line = next((line for line in content.splitlines() if line.strip()), "")
        if first_non_empty_line.count(";") > first_non_empty_line.count(","):
            return ";"
        return ","

    def _should_skip_import_row(self, row):
        values = [(value or "").strip() for value in row.values()]
        if not any(values):
            return True
        if all(value in {"```", "'''"} for value in values if value):
            return True
        return False


class LeadSourceViewSet(OrganizationScopedBaseViewSet):
    serializer_class = LeadSourceSerializer
    permission_classes = [LeadConfigurationPermission]
    filter_backends = [drf_filters.SearchFilter, drf_filters.OrderingFilter]
    search_fields = ["name"]
    ordering_fields = ["name", "created_at", "updated_at"]
    ordering = ["name"]

    def get_queryset(self):
        return LeadSource.objects.filter(organization=self.get_organization()).order_by(*self.ordering)

    def perform_create(self, serializer):
        serializer.save(organization=self.get_organization())


class TagViewSet(OrganizationScopedBaseViewSet):
    serializer_class = TagSerializer
    permission_classes = [LeadConfigurationPermission]
    filter_backends = [drf_filters.SearchFilter, drf_filters.OrderingFilter]
    search_fields = ["name", "color"]
    ordering_fields = ["name", "created_at", "updated_at"]
    ordering = ["name"]

    def get_queryset(self):
        return Tag.objects.filter(organization=self.get_organization()).order_by(*self.ordering)

    def perform_create(self, serializer):
        serializer.save(organization=self.get_organization())
