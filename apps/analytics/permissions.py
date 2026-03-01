from rest_framework.permissions import BasePermission

from apps.core.permissions import HasOrganizationAccess


class AnalyticsAccessPermission(BasePermission):
    message = "You do not have permission to access analytics."

    def has_permission(self, request, view):
        return HasOrganizationAccess().has_permission(request, view)
