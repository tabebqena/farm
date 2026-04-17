from django.contrib import admin

from .models import Adjustment


@admin.register(Adjustment)
class AdjustmentAdmin(admin.ModelAdmin):
    list_display = ["id", "operation", "type", "amount", "date", "officer"]
    list_filter = ["type"]
    readonly_fields = ["created_at", "updated_at"]
