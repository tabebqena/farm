from django.contrib import admin

from .models import InvoiceItem, ProductTemplate


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1
    fields = ("product", "description", "quantity", "unit_price")


admin.site.register(ProductTemplate)
