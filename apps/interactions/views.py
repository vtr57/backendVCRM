from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.response import Response

from apps.interactions.filters import InteractionFilter
from apps.interactions.models import Interaction
from apps.interactions.permissions import InteractionAccessPermission
from apps.interactions.serializers import InteractionSerializer, InteractionWriteSerializer
from apps.interactions.services import filter_interactions_for_membership, sync_lead_last_interaction


class InteractionViewSet(viewsets.ModelViewSet):
    permission_classes = [InteractionAccessPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_class = InteractionFilter

    def get_queryset(self):
        queryset = (
            Interaction.objects.filter(organization=self.request.organization)
            .select_related("lead", "deal", "created_by")
            .order_by("-occurred_at", "-created_at")
        )
        return filter_interactions_for_membership(queryset, self.request)

    def get_serializer_class(self):
        if self.action in {"list", "retrieve"}:
            return InteractionSerializer
        return InteractionWriteSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        output = InteractionSerializer(serializer.instance, context=self.get_serializer_context())
        headers = self.get_success_headers(output.data)
        return Response(output.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        instance.refresh_from_db()
        output = InteractionSerializer(instance, context=self.get_serializer_context())
        return Response(output.data)

    def perform_destroy(self, instance):
        lead = instance.lead
        instance.delete()
        sync_lead_last_interaction(lead)
