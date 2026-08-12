from django.urls import path

from . import views

# TODO view for list product templates
# Todo

urlpatterns = [
    path(
        "entity/<int:entity_pk>/stock/",
        views.stock_detail,
        name="stock_detail",
    ),
    path(
        "entity/<int:entity_pk>/stock/history/",
        views.stock_history,
        name="stock_history",
    ),
    path(
        "entity/<int:entity_pk>/stock/consume/",
        views.quick_consume,
        name="quick_consume",
    ),
    path(
        "products/<int:pk>/",
        views.product_detail,
        name="product_detail",
    ),
    # Product templates
    path(
        "entity/<int:entity_pk>/product-templates/",
        views.entity_product_templates_list,
        name="entity_product_templates_list",
    ),
    path(
        "entity/<int:entity_pk>/product-templates/manage/",
        views.project_product_templates_setup,
        name="entity_product_templates_setup",
    ),
    path(
        "product-templates/<int:pk>/",
        views.product_template_detail,
        name="product_template_detail",
    ),
    path(
        "product-templates/create/",
        views.create_product_template,
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
        views.create_purchase_movement,
        name="create_purchase_movement",
    ),
    path(
        "operations/<int:operation_pk>/movement/create/sale/",
        views.create_sale_movement,
        name="create_sale_movement",
    ),
    # Backwards-compatible route for the pre-split URL (redirects to the
    # type-specific view).
    path(
        "operations/<int:operation_pk>/movement/create/",
        views.create_inventory_movement,
        name="create_inventory_movement",
    ),
    path(
        "movement-lines/<int:pk>/reverse/",
        views.reverse_inventory_movement_line,
        name="reverse_inventory_movement_line",
    ),
    path(
        "movement-lines/batch-reverse/<str:group_key>/",
        views.batch_reverse_inventory_movement_lines,
        name="batch_reverse_inventory_movement_lines",
    ),
    # Deferred movement registration
    path(
        "operations/<int:operation_pk>/movement/deferred/",
        views.register_deferred_movements,
        name="register_deferred_movements",
    ),
]
