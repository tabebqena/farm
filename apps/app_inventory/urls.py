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
    # Movement line
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
        "movements/<int:pk>/reverse/",
        views.reverse_inventory_movement,
        name="reverse_inventory_movement",
    ),
]
