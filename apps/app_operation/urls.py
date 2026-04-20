from django.urls import path

from . import views

urlpatterns = [
    path(
        "<int:person_pk>/list/",
        views.operation_list_view,
        name="operation_list_view",
    ),
    path(
        "<int:pk>/evaluate/<int:product_pk>/",
        views.EvaluationCreateView.as_view(),
        name="evaluation_create_view",
    ),
    path(
        "<int:pk>/birth/create",
        views.BirthCreateView.as_view(),
        name="birth_create_view",
    ),
    path(
        "<int:pk>/death/create",
        views.DeathCreateView.as_view(),
        name="death_create_view",
    ),
    # path(
    #     "<int:pk>/purchase/create",
    #     views.PurchaseCreateView.as_view(),
    #     name="purchase_create_view",
    # ),
    # Just for testing
    path(
        "<int:pk>/purchase/wizard/",
        views.purchase_wizard_view,
        # name="purchase_wizard_step1",
        name="purchase_create_view",
    ),
    path(
        "<int:pk>/purchase/wizard/2/",
        views.purchase_wizard_view,
        name="purchase_wizard_step2_new",
    ),
    path(
        "<int:pk>/purchase/wizard/<int:operation_pk>/<int:step>/",
        views.purchase_wizard_view,
        name="purchase_wizard_step",
    ),
    path(
        "<int:pk>/sale/create",
        views.SaleCreateView.as_view(),
        name="sale_create_view",
    ),
    path(
        "<int:pk>/<op_type>/create",
        views.OperationCreateView.as_view(),
        name="operation_create_view",
    ),
    path(
        "repayment/<int:pk>/create",
        views.record_transaction_repayment,
        name="record_transaction_repayment",
    ),
    path(
        "payment/<int:pk>/create",
        views.record_transaction_payment,
        name="record_transaction_payment",
    ),
    path(
        "<int:pk>/detail/",
        views.operation_detail_view,
        name="operation_detail_view",
    ),
    path(
        "<int:pk>/reverse/",
        views.operation_reverse_view,
        name="operation_reverse_view",
    ),
    path(
        "<int:pk>/edit/",
        views.operation_update_view,
        name="operation_update_view",
    ),
    path(
        "category/add/<int:parent_entity_id>",
        views.category_create_view,
        name="category_create",
    ),
    path(
        "category/edit/<int:pk>",
        views.category_edit_view,
        name="category_edit",
    ),
    path(
        "category/detail/<int:pk>",
        views.category_detail_view,
        name="category_detail",
    ),
    path(
        "category/bulk-create/<int:parent_entity_id>",
        views.category_bulk_create_view,
        name="category_bulk_create",
    ),
]
