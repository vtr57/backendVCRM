from django.contrib import admin

from apps.pipeline.models import Deal, Pipeline, Stage, StageMovement


@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "is_default", "is_active", "created_at")
    list_filter = ("organization", "is_default", "is_active")
    search_fields = ("name", "organization__name", "organization__slug")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    list_display = ("name", "pipeline", "order", "kind", "probability", "color", "wip_limit")
    list_filter = ("pipeline", "kind")
    search_fields = ("name", "slug", "pipeline__name", "pipeline__organization__name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "organization",
        "pipeline",
        "stage",
        "lead",
        "owner",
        "status",
        "amount",
        "expected_close_date",
        "closed_at",
    )
    list_filter = ("organization", "pipeline", "stage", "status", "owner", "created_by")
    search_fields = ("title", "lead__full_name", "lead__company_name", "owner__email")
    readonly_fields = ("created_at", "updated_at", "closed_at")


@admin.register(StageMovement)
class StageMovementAdmin(admin.ModelAdmin):
    list_display = ("deal", "organization", "from_stage", "to_stage", "moved_by", "moved_at")
    list_filter = ("organization", "to_stage", "moved_by")
    search_fields = ("deal__title", "deal__lead__full_name", "moved_by__email", "note")
    readonly_fields = ("moved_at",)
