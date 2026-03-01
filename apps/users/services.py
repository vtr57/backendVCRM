from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.users.models import Membership, Organization


def resolve_membership_for_request(request, user):
    organization = getattr(request, "organization", None)
    header_used = getattr(request, "organization_header_used", None)
    organization_error = getattr(request, "organization_resolution_error", None)

    memberships = Membership.objects.select_related("organization").filter(
        user=user,
        is_active=True,
        organization__is_active=True,
    )

    if organization_error == "not_found":
        raise NotFound("Organization not found.")

    if organization is not None:
        membership = memberships.filter(organization=organization).first()
        if membership is None:
            raise PermissionDenied("You do not have access to this organization.")
        return membership

    membership = memberships.filter(is_default=True).first()
    if membership is not None:
        return membership

    membership = memberships.order_by("organization__name").first()
    if membership is not None:
        return membership

    if header_used:
        raise PermissionDenied("You do not have access to this organization.")

    raise PermissionDenied("No active organization membership is available for this user.")


def resolve_organization_by_lookup(identifier=None, slug=None):
    queryset = Organization.objects.filter(is_active=True)

    if identifier:
        try:
            return queryset.filter(id=identifier).first()
        except (DjangoValidationError, ValueError):
            return None

    if slug:
        return queryset.filter(slug=slug).first()

    return None
