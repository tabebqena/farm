from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Adjustment, AdjustmentType


class FinancialAdjustmentTypeFilter(admin.SimpleListFilter):
    """Show only user-facing financial adjustment types in the admin filter,
    excluding internal item-correction types."""

    title = _("type")
    parameter_name = "type"

    def lookups(self, request, model_admin):
        return [
            (t.value, t.label)
            for t in AdjustmentType
            if not AdjustmentType.is_item_correction(t)
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(type=self.value())
        return queryset


@admin.register(Adjustment)
class AdjustmentAdmin(admin.ModelAdmin):
    list_display = ["id", "operation", "type", "amount", "date", "officer"]
    list_filter = [FinancialAdjustmentTypeFilter]
    readonly_fields = ["created_at", "updated_at"]
