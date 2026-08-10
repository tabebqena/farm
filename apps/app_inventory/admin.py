from django.contrib import admin

from .models import (
    InvoiceItem,
    MedicalRecord,
    Product,
    ProductTemplate,
)


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1
    fields = ("product", "description", "quantity", "unit_price")


class MedicalRecordInline(admin.TabularInline):
    model = MedicalRecord
    extra = 0
    fields = ("date", "record_type", "status", "next_due_date", "notes", "officer")


@admin.register(ProductTemplate)
class ProductTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "nature",
        "animal_type",
        "gender",
        "sub_category",
        "can_die",
        "can_be_consumed",
        "default_unit",
    )
    list_filter = ("nature", "gender", "can_die", "can_be_consumed")
    search_fields = ("name", "animal_type", "tag_prefix")
    filter_horizontal = ("produces",)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "name_ar",
                    "nature",
                    "sub_category",
                    "default_unit",
                )
            },
        ),
        (
            "Tagging",
            {"fields": ("has_tag", "tag_prefix", "minimum_quantity")},
        ),
        (
            "Animal attributes",
            {
                "fields": (
                    "animal_type",
                    "gender",
                    "produces",
                    "gives_birth_to",
                    "can_die",
                    "can_be_consumed",
                ),
                "classes": ("wide",),
            },
        ),
        ("Entities", {"fields": ("entities",)}),
    )


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "unique_id",
        "product_template",
        "entity",
        "gender",
        "birth_date",
        "mother",
        "quantity",
        "unit_price",
    )
    list_filter = ("product_template__nature", "gender")
    search_fields = ("unique_id", "product_template__name")
    raw_id_fields = ("entity", "mother")
    inlines = [MedicalRecordInline]


@admin.register(MedicalRecord)
class MedicalRecordAdmin(admin.ModelAdmin):
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
