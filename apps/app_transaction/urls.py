from django.urls import path

from . import views

urlpatterns = [
    path(
        "entity/<int:entity_pk>/",
        views.entity_transactions_view,
        name="entity_transactions_list",
    ),
    path(
        "<int:pk>/reverse/",
        views.transaction_reverse_view,
        name="transaction_reverse_view",
    ),
]
