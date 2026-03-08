from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.interactions.serializers import InteractionSerializer
from apps.interactions.services import filter_interactions_for_membership
from apps.pipeline.models import Deal, Pipeline, Stage
from apps.pipeline.permissions import PipelineAccessPermission, PipelineConfigurationPermission
from apps.pipeline.serializers import (
    BoardStageSerializer,
    DealDetailSerializer,
    DealListSerializer,
    DealMoveSerializer,
    DealWriteSerializer,
    PipelineSerializer,
    StageMovementSerializer,
    StageSerializer,
)
from apps.pipeline.services import (
    build_individual_deal_scope,
    ensure_user_can_access_deal,
    get_default_pipeline_for_organization,
    move_deal,
    resolve_board_member_user,
    seed_pipeline_stages,
)
from apps.users.models import Membership


class OrganizationScopedViewSet(viewsets.ModelViewSet):
    def get_organization(self):
        return self.request.organization


class PipelineViewSet(OrganizationScopedViewSet):
    serializer_class = PipelineSerializer
    permission_classes = [PipelineConfigurationPermission]

    def get_queryset(self):
        return Pipeline.objects.filter(organization=self.get_organization()).order_by("name")

    def perform_create(self, serializer):
        is_default = serializer.validated_data.get("is_default", False)
        if is_default:
            Pipeline.objects.filter(organization=self.get_organization(), is_default=True).update(
                is_default=False
            )
        pipeline = serializer.save(organization=self.get_organization())
        seed_pipeline_stages(pipeline)

    def perform_update(self, serializer):
        is_default = serializer.validated_data.get("is_default")
        if serializer.instance.is_default and is_default is False:
            raise ValidationError({"is_default": "An organization must always have a default pipeline."})
        if is_default:
            Pipeline.objects.filter(organization=self.get_organization(), is_default=True).exclude(
                id=serializer.instance.id
            ).update(is_default=False)
        serializer.save()

    @action(detail=False, methods=["get"], permission_classes=[PipelineAccessPermission])
    def board(self, request):
        pipeline_id = request.query_params.get("pipeline_id")
        member_user_id = request.query_params.get("member_user_id")
        if pipeline_id:
            pipeline = get_object_or_404(
                Pipeline,
                id=pipeline_id,
                organization=self.get_organization(),
            )
        else:
            pipeline = get_default_pipeline_for_organization(self.get_organization())

        stages = list(pipeline.stages.order_by("order"))
        deals_queryset = (
            Deal.objects.filter(organization=self.get_organization(), pipeline=pipeline)
            .select_related("lead", "owner", "stage")
            .order_by("stage__order", "position", "-created_at")
        )

        membership = request.membership
        board_member = resolve_board_member_user(
            organization=self.get_organization(),
            membership=membership,
            request_user=request.user,
            member_user_id=member_user_id,
        )
        deals_queryset = deals_queryset.filter(build_individual_deal_scope(board_member)).distinct()

        deal_map = {stage.id: [] for stage in stages}
        for deal in deals_queryset:
            deal_map.setdefault(deal.stage_id, []).append(deal)

        data = {
            "pipeline": PipelineSerializer(pipeline).data,
            "stages": BoardStageSerializer(stages, many=True, context={"deal_map": deal_map}).data,
        }
        return Response(data)


class StageViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StageSerializer
    permission_classes = [PipelineAccessPermission]

    def get_queryset(self):
        queryset = Stage.objects.filter(pipeline__organization=self.request.organization).select_related(
            "pipeline"
        )
        pipeline_id = self.request.query_params.get("pipeline_id")
        if pipeline_id:
            queryset = queryset.filter(pipeline_id=pipeline_id)
        return queryset.order_by("pipeline__name", "order")


class DealViewSet(OrganizationScopedViewSet):
    permission_classes = [PipelineAccessPermission]

    def get_queryset(self):
        queryset = (
            Deal.objects.filter(organization=self.get_organization())
            .select_related("lead", "lead__assigned_to", "owner", "created_by", "stage", "pipeline")
            .order_by("stage__order", "position", "-created_at")
        )

        membership = self.request.membership
        if membership.role == Membership.Role.SALES:
            queryset = queryset.filter(
                Q(owner=self.request.user)
                | Q(created_by=self.request.user)
                | Q(lead__created_by=self.request.user)
                | Q(lead__assigned_to=self.request.user)
            )
        return queryset.distinct()

    def get_serializer_class(self):
        if self.action == "list":
            return DealListSerializer
        if self.action == "retrieve":
            return DealDetailSerializer
        if self.action == "move":
            return DealMoveSerializer
        return DealWriteSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        output = DealDetailSerializer(serializer.instance, context=self.get_serializer_context())
        headers = self.get_success_headers(output.data)
        return Response(output.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        instance.refresh_from_db()
        output = DealDetailSerializer(instance, context=self.get_serializer_context())
        return Response(output.data)

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        deal = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        stage = get_object_or_404(
            Stage,
            id=serializer.validated_data["stage_id"],
            pipeline=deal.pipeline,
        )
        moved_deal = move_deal(
            deal=deal,
            target_stage=stage,
            moved_by=request.user,
            target_position=serializer.validated_data.get("position"),
            note=serializer.validated_data.get("note", ""),
            lost_reason=serializer.validated_data.get("lost_reason", ""),
        )
        output = DealDetailSerializer(moved_deal, context=self.get_serializer_context())
        return Response(output.data)

    @action(detail=True, methods=["get"])
    def movements(self, request, pk=None):
        deal = self.get_object()
        ensure_user_can_access_deal(request.membership, request.user, deal)
        queryset = deal.movements.select_related("from_stage", "to_stage", "moved_by").all()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = StageMovementSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = StageMovementSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def timeline(self, request, pk=None):
        deal = self.get_object()
        ensure_user_can_access_deal(request.membership, request.user, deal)
        queryset = filter_interactions_for_membership(
            deal.interactions.select_related("lead", "created_by").all(),
            request,
        )
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = InteractionSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = InteractionSerializer(queryset, many=True)
        return Response(serializer.data)
