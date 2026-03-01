from django.contrib import admin

from apps.interactions.models import Interaction


@admin.register(Interaction)
class InteractionAdmin(admin.ModelAdmin):
    list_display = ("type", "direction", "lead", "deal", "created_by", "occurred_at", "organization")
    list_filter = ("organization", "type", "direction", "created_by")
    search_fields = ("lead__full_name", "deal__title", "subject", "content", "outcome", "created_by__email")
    readonly_fields = ("created_at", "updated_at", "occurred_at")
