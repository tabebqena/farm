from django.urls import path

from . import views

urlpatterns = [
    path(
        "<int:pk>/reverse/",
        views.transaction_reverse_view,
        name="transaction_reverse_view",
    ),
]
