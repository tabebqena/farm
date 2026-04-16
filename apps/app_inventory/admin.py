from django.contrib import admin

from .models import Invoice, InvoiceItem, ProductTemplate


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1
    fields = ("product", "description", "quantity", "unit_price")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    inlines = [InvoiceItemInline]
    list_display = ("id", "operation", "total_price")


admin.site.register(ProductTemplate)
