"""URL routing for the report app (report hub + financial statement views)."""

from django.urls import path

from . import views

urlpatterns = [
    path(
        "<int:entity_pk>/",
        views.ReportsHubView.as_view(),
        name="report_hub",
    ),
    path(
        "<int:entity_pk>/income-statement/",
        views.IncomeStatementView.as_view(),
        name="income_statement",
    ),
    path(
        "<int:entity_pk>/balance-sheet/",
        views.BalanceSheetView.as_view(),
        name="balance_sheet",
    ),
    path(
        "<int:entity_pk>/cash-flow/",
        views.CashFlowView.as_view(),
        name="cash_flow",
    ),
    path(
        "<int:entity_pk>/equity/",
        views.EquityStatementView.as_view(),
        name="equity_statement",
    ),
]
