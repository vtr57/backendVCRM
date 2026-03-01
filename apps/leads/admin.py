from django.contrib import admin

from apps.leads.models import Lead, LeadSource, Tag


@admin.register(LeadSource)
class LeadSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "is_active", "created_at")
    list_filter = ("is_active", "organization")
    search_fields = ("name", "organization__name", "organization__slug")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "color", "created_at")
    list_filter = ("organization",)
    search_fields = ("name", "organization__name", "organization__slug")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "company_name",
        "email",
        "phone",
        "organization",
        "status",
        "temperature",
        "assigned_to",
        "source",
        "estimated_value",
        "created_at",
    )
    list_filter = ("organization", "status", "temperature", "source", "assigned_to", "created_by")
    search_fields = ("full_name", "email", "phone", "company_name", "job_title")
    readonly_fields = ("created_at", "updated_at", "deleted_at", "last_interaction_at")
    filter_horizontal = ("tags",)

