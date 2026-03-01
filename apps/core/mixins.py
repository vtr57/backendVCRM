class OrganizationScopedQuerysetMixin:
    def get_organization(self):
        if getattr(self.request, "organization", None) is None:
            raise AttributeError("Request organization is not available.")
        return self.request.organization

    def get_queryset(self):
        queryset = super().get_queryset()
        organization_field = getattr(self, "organization_field", "organization")
        return queryset.filter(**{organization_field: self.get_organization()})
