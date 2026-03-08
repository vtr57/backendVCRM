from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.core.permissions import HasOrganizationAccess
from apps.users.models import Membership


class LeadAccessPermission(BasePermission):
    message = "You do not have permission to access this lead."

    def has_permission(self, request, view):
        return HasOrganizationAccess().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        membership = getattr(request, "membership", None)
        if membership is None:
            return False

        if membership.role in {
            Membership.Role.OWNER,
            Membership.Role.ADMIN,
        }:
            return True

        if membership.role == Membership.Role.SALES:
            if request.method in SAFE_METHODS:
                return obj.created_by_id == request.user.id or obj.assigned_to_id == request.user.id
            return obj.created_by_id == request.user.id or obj.assigned_to_id == request.user.id

        return False


class LeadConfigurationPermission(BasePermission):
    message = "You do not have permission to manage lead settings."

    def has_permission(self, request, view):
        if not HasOrganizationAccess().has_permission(request, view):
            return False

        membership = getattr(request, "membership", None)
        if membership is None:
            return False

        if request.method in SAFE_METHODS:
            return True

        return membership.role in {
            Membership.Role.OWNER,
            Membership.Role.ADMIN,
        }
