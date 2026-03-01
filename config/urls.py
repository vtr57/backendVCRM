from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.core.urls")),
    path("api/v1/", include("apps.users.urls")),
    path("api/v1/", include("apps.leads.urls")),
    path("api/v1/", include("apps.pipeline.urls")),
    path("api/v1/", include("apps.interactions.urls")),
    path("api/v1/", include("apps.analytics.urls")),
]
