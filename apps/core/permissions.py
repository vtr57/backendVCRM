from rest_framework.permissions import BasePermission

from apps.users.services import resolve_membership_for_request


class HasOrganizationAccess(BasePermission):
    message = "You do not have access to this organization."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        membership = resolve_membership_for_request(request, request.user)
        request.organization = membership.organization
        request.membership = membership
        return True
