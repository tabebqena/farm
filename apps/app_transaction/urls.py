from django.urls import path

from . import views

urlpatterns = [
    path(
        "entity/<int:entity_pk>/",
        views.entity_payment_transactions_view,
        name="entity_payment_transactions_list",
    ),
    path(
        "entity/<int:entity_pk>/payables/",
        views.entity_payables_view,
        name="entity_payables_list",
    ),
    path(
        "entity/<int:entity_pk>/receivables/",
        views.entity_receivables_view,
        name="entity_receivables_list",
    ),
    path(
        "transaction/<int:transaction_pk>/",
        views.transaction_detail_view,
        name="transaction_detail",
    ),
    path(
        "<int:pk>/reverse/",
        views.transaction_reverse_view,
        name="transaction_reverse_view",
    ),
]
