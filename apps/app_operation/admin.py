from django.contrib import admin

from .models.operation import Operation
from .models.period import FinancialPeriod


@admin.register(Operation)
class OpeartionAdmin(admin.ModelAdmin):
    pass


@admin.register(FinancialPeriod)
class FinancialPeriodAdmin(admin.ModelAdmin):
    list_display = ("entity", "start_date", "end_date", "is_closed")
    list_filter = ("end_date",)
    readonly_fields = ("entity", "start_date")

    @admin.display(boolean=True)
    def is_closed(self, obj):
        return obj.is_closed
