from django.urls import path

from . import views

urlpatterns = [
    path(
        "stock/",
        views.stock_detail,
        name="stock_detail",
    ),
    path(
        "products/<int:pk>/",
        views.product_detail,
        name="product_detail",
    ),
    path(
        "invoices/<int:pk>/",
        views.invoice_detail,
        name="invoice_detail",
    ),
    path(
        "entity/<int:entity_pk>/product-templates",
        views.project_product_templates_setup,
        name="entity_product_templates_setup",
    ),
    path(
        "product-templates/create/",
        views.create_product_template,
        name="create_product_template",
    ),
]
