"""Admin configuration for the animal-health app.

Registers :class:`MedicalRecord` with list/search/filter options for browsing
veterinary records.
"""

from django.contrib import admin

from .models import MedicalRecord


@admin.register(MedicalRecord)
class MedicalRecordAdmin(admin.ModelAdmin):
    """Admin for :class:`MedicalRecord` with list/filter/search options."""

    list_display = (
        "product",
        "date",
        "record_type",
        "status",
        "next_due_date",
        "officer",
    )
    list_filter = ("record_type", "status")
    search_fields = ("product__unique_id", "product__product_template__name", "notes")
    raw_id_fields = ("product", "officer")
