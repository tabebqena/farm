from django.urls import path

from . import views

urlpatterns = [
    path(
        "<int:entity_pk>/",
        views.reports_hub_view,
        name="report_hub",
    ),
    path(
        "<int:entity_pk>/income-statement/",
        views.income_statement_view,
        name="income_statement",
    ),
    path(
        "<int:entity_pk>/balance-sheet/",
        views.balance_sheet_view,
        name="balance_sheet",
    ),
    path(
        "<int:entity_pk>/cash-flow/",
        views.cash_flow_view,
        name="cash_flow",
    ),
    path(
        "<int:entity_pk>/equity/",
        views.equity_statement_view,
        name="equity_statement",
    ),
]
