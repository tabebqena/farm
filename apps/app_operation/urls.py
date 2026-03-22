from django.urls import path

from . import views

urlpatterns = [
    # Reversal View
    # path(
    #     'ops/<int:pk>/reverse/',
    #     views.operation_reverse_view,
    #     name='operation_reverse'
    # ),
    # path(
    #     "<int:person_pk>/capital-history/",
    #     views.cash_list_view,
    #     name="cash_list_view",
    # ),
    #
    path(
        "<int:person_pk>/capital-history/",
        views.operation_list_view,
        name="cash_list_view",
    ),
    path(
        "<int:pk>/<op_type>/create",
        views.operation_create_factory,
        name="operation_create_view",
    ),
    path(
        "repayment/<int:pk>/create",
        views.record_transaction_repayment,
        name="loan_repayment_view",
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
    #
    # path(
    #     "<int:pk>/reverse",
    #     views.cash_injection_reverse_view,
    #     name="cash_injection_reverse_view",
    # ),
    # path(
    #     "injection/<int:pk>/",
    #     views.CashInjectionDetailView.as_view(),
    #     name="cash_injection_detail_view",
    # ),
    # path(
    #     "injection/<int:pk>/edit/",
    #     views.CashInjectionUpdateView.as_view(),
    #     name="cash_injection_update_view",
    # ),
]
