from apps.users.services import resolve_organization_by_lookup


class OrganizationContextMiddleware:
    header_id = "HTTP_X_ORGANIZATION_ID"
    header_slug = "HTTP_X_ORGANIZATION_SLUG"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.organization = None
        request.membership = None
        request.organization_header_used = None
        request.organization_resolution_error = None

        organization_id = request.META.get(self.header_id)
        organization_slug = request.META.get(self.header_slug)

        if organization_id:
            request.organization_header_used = "id"
            request.organization = resolve_organization_by_lookup(identifier=organization_id)
        elif organization_slug:
            request.organization_header_used = "slug"
            request.organization = resolve_organization_by_lookup(slug=organization_slug)

        if request.organization is None and request.organization_header_used is not None:
            request.organization_resolution_error = "not_found"

        return self.get_response(request)
