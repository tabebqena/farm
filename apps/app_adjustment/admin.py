from django.contrib import admin

from .models import Adjustment


@admin.register(Adjustment)
class AdjustmentAdmin(admin.ModelAdmin):
    list_display = ["id", "operation", "type", "amount", "effect", "date", "officer"]
    list_filter = ["type", "effect"]
    readonly_fields = ["effect", "created_at", "updated_at"]
