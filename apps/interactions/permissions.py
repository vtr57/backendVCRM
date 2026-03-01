from rest_framework.permissions import BasePermission
from rest_framework.exceptions import ValidationError

from apps.core.permissions import HasOrganizationAccess
from apps.pipeline.services import ensure_user_can_access_deal, ensure_user_can_access_lead


class InteractionAccessPermission(BasePermission):
    message = "You do not have permission to access this interaction."

    def has_permission(self, request, view):
        return HasOrganizationAccess().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        try:
            ensure_user_can_access_lead(request.membership, request.user, obj.lead)
            if obj.deal_id:
                ensure_user_can_access_deal(request.membership, request.user, obj.deal)
        except ValidationError:
            return False
        return True
