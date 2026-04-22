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
        name="purchase_wizard_step1",
    ),
    path(
        "<int:pk>/purchase/wizard/cancel/",
        views.cancel_purchase_wizard_view,
        name="purchase_wizard_cancel",
    ),
    path(
        "<int:pk>/purchase/wizard/<int:step>/",
        views.purchase_wizard_view,
        name="purchase_wizard_step_new",
    ),
    path(
        "<int:pk>/purchase/invoice/",
        views.purchase_invoice_view,
        name="purchase_invoice",
    ),
    path(
        "<int:pk>/purchase/invoice/select-template/",
        views.purchase_select_template_view,
        name="purchase_select_template",
    ),
    path(
        "<int:pk>/purchase/invoice/add-item/",
        views.purchase_add_item_view,
        name="purchase_add_item",
    ),
    path(
        "<int:pk>/purchase/invoice/add-item/<int:idx>/",
        views.purchase_add_item_view,
        name="purchase_edit_item",
    ),
    path(
        "<int:pk>/purchase/invoice/delete-item/<int:idx>/",
        views.purchase_delete_item_view,
        name="purchase_delete_item",
    ),
    path(
        "<int:pk>/purchase/invoice/submit/",
        views.purchase_submit_view,
        name="purchase_submit",
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
]
