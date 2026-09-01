from django.urls import path

from . import views

urlpatterns = [
    path(
        "entity/<int:entity_pk>/",
        views.EntityPaymentTransactionsView.as_view(),
        name="entity_payment_transactions_list",
    ),
    path(
        "entity/<int:entity_pk>/payables/",
        views.EntityPayablesView.as_view(),
        name="entity_payables_list",
    ),
    path(
        "entity/<int:entity_pk>/receivables/",
        views.EntityReceivablesView.as_view(),
        name="entity_receivables_list",
    ),
    path(
        "transaction/<int:transaction_pk>/",
        views.TransactionDetailView.as_view(),
        name="transaction_detail",
    ),
    path(
        "<int:pk>/reverse/",
        views.TransactionReverseView.as_view(),
        name="transaction_reverse_view",
    ),
]
