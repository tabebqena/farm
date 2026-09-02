"""URL routing for the inventory app.

Covers stock detail / history / quick-consume, product and product-template
pages, purchase and sale inventory-movement creation, movement-line reversal,
and deferred movement registration.
"""

from django.urls import path

from . import views

# TODO view for list product templates
# Todo

urlpatterns = [
    path(
        "entity/<int:entity_pk>/stock/",
        views.StockDetailView.as_view(),
        name="stock_detail",
    ),
    path(
        "entity/<int:entity_pk>/stock/history/",
        views.StockHistoryView.as_view(),
        name="stock_history",
    ),
    path(
        "entity/<int:entity_pk>/stock/consume/",
        views.QuickConsumeView.as_view(),
        name="quick_consume",
    ),
    path(
        "products/<int:pk>/",
        views.ProductDetailView.as_view(),
        name="product_detail",
    ),
    # Product templates
    path(
        "entity/<int:entity_pk>/product-templates/",
        views.EntityProductTemplatesListView.as_view(),
        name="entity_product_templates_list",
    ),
    path(
        "entity/<int:entity_pk>/product-templates/manage/",
        views.ProjectProductTemplatesSetupView.as_view(),
        name="entity_product_templates_setup",
    ),
    path(
        "product-templates/<int:pk>/",
        views.ProductTemplateDetailView.as_view(),
        name="product_template_detail",
    ),
    path(
        "product-templates/create/",
        views.CreateProductTemplateView.as_view(),
        name="create_product_template",
    ),
    # TODO don't add edit view for product templates,
    # As templates are shared betwenn projects.
    # Never allow the user to edit the templates based on one
    # of his current project.
    # Movement line — PURCHASE (receive) and SALE (dispatch) are separate
    # flows so each only ever applies to its own operation type.
    path(
        "operations/<int:operation_pk>/movement/create/purchase/",
        views.CreatePurchaseMovementView.as_view(),
        name="create_purchase_movement",
    ),
    path(
        "operations/<int:operation_pk>/movement/create/sale/",
        views.CreateSaleMovementView.as_view(),
        name="create_sale_movement",
    ),
    # Backwards-compatible route for the pre-split URL (redirects to the
    # type-specific view).
    path(
        "operations/<int:operation_pk>/movement/create/",
        views.CreateInventoryMovementRedirectView.as_view(),
        name="create_inventory_movement",
    ),
    path(
        "movement-lines/<int:pk>/reverse/",
        views.ReverseInventoryMovementLineView.as_view(),
        name="reverse_inventory_movement_line",
    ),
    path(
        "movement-lines/batch-reverse/<str:group_key>/",
        views.BatchReverseInventoryMovementLinesView.as_view(),
        name="batch_reverse_inventory_movement_lines",
    ),
    # Deferred movement registration
    path(
        "operations/<int:operation_pk>/movement/deferred/",
        views.RegisterDeferredMovementsView.as_view(),
        name="register_deferred_movements",
    ),
]
