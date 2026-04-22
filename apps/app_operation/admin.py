from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from apps.app_entity.models import EntityType

from .models.operation import Operation
from .models.period import FinancialPeriod


@admin.register(Operation)
class OpeartionAdmin(admin.ModelAdmin):
    readonly_fields = ("source_link", "destination_link")
    fieldsets = (
        ("Entities", {"fields": ("source_link", "destination_link")}),
        ("Operation Details", {"fields": ("operation_type", "amount", "date", "description")}),
        ("Period & Plan", {"fields": ("period", "plan")}),
        ("Officer", {"fields": ("officer",)}),
    )

    def source_link(self, obj):
        if obj.source.entity_type in (EntityType.SYSTEM, EntityType.WORLD):
            return obj.source.name
        url = reverse(
            "admin:app_entity_entity_change",
            args=[obj.source.pk],
        )
        return format_html(
            '<a href="{}">{}</a>',
            url,
            obj.source.name,
        )

    source_link.short_description = "Source"

    def destination_link(self, obj):
        if obj.destination.entity_type in (
            EntityType.SYSTEM,
            EntityType.WORLD,
        ):
            return obj.destination.name
        url = reverse(
            "admin:app_entity_entity_change",
            args=[obj.destination.pk],
        )
        return format_html(
            '<a href="{}">{}</a>',
            url,
            obj.destination.name,
        )

    destination_link.short_description = "Destination"


@admin.register(FinancialPeriod)
class FinancialPeriodAdmin(admin.ModelAdmin):
    list_display = ("entity", "start_date", "end_date", "is_closed")
    list_filter = ("end_date",)
    readonly_fields = ("entity", "start_date")

    @admin.display(boolean=True)
    def is_closed(self, obj):
        return obj.is_closed
