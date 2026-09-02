"""Report views.

Provides the report hub and the financial-statement views — income statement
(P&L), balance sheet, cash-flow statement and statement of changes in equity —
scoped to an entity and its selected financial period. Statement data is built
in :mod:`apps.app_report.reporting`.
"""

from datetime import date

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.views import View

from apps.app_base.logging_utils import logger
from apps.app_base.navigation import set_entity_navigation
from apps.app_entity.models import Entity
from apps.app_operation.models.period import FinancialPeriod
from farm.shortcuts import get_object_or_404

from . import reporting


class _ReportBaseView(LoginRequiredMixin, View):
    """Shared plumbing for report views (login + entity/period resolution)."""

    template_name: str

    def _resolve(self, entity_pk):
        """Load the entity, its periods, and the selected/default period."""
        logger.debug(f"Resolving report scope | entity_pk={entity_pk}")
        entity = get_object_or_404(
            Entity,
            pk=entity_pk,
            error_message="Entity not found or has been deleted.",
        )
        periods = list(entity.financial_periods.all().order_by("-start_date"))
        period_pk = self.request.GET.get("period")
        if period_pk:
            period = get_object_or_404(
                FinancialPeriod,
                pk=period_pk,
                entity=entity,
                error_message="Financial period not found for this entity.",
            )
        else:
            period = next((p for p in periods if p.end_date is None), None) or (
                periods[0] if periods else None
            )
        return entity, periods, period

    def _base_context(self, entity, periods, period):
        set_entity_navigation(self.request, entity)
        return {
            "entity": entity,
            "periods": periods,
            "period": period,
            "today": date.today(),
            "currency": getattr(settings, "CURRENCY_SYMBOL", "$"),
        }

    def get(self, request, *args, **kwargs):
        entity, periods, period = self._resolve(kwargs["entity_pk"])
        context = self._base_context(entity, periods, period)
        return render(request, self.template_name, context)


class ReportsHubView(_ReportBaseView):
    """Financial Reports hub for an entity."""

    template_name = "app_report/report_hub.html"


class IncomeStatementView(_ReportBaseView):
    """Income Statement (P&L) for a project period."""

    template_name = "app_report/income_statement.html"

    def get(self, request, *args, **kwargs):
        entity, periods, period = self._resolve(kwargs["entity_pk"])
        if not entity.is_project:
            raise PermissionDenied(
                "The Income Statement is only available for project entities."
            )
        context = self._base_context(entity, periods, period)
        context["statement"] = reporting.income_statement(period) if period else None
        return render(request, self.template_name, context)


class BalanceSheetView(_ReportBaseView):
    """Balance Sheet for a project period."""

    template_name = "app_report/balance_sheet.html"

    def get(self, request, *args, **kwargs):
        entity, periods, period = self._resolve(kwargs["entity_pk"])
        if not entity.is_project:
            raise PermissionDenied(
                "The Balance Sheet is only available for project entities."
            )
        context = self._base_context(entity, periods, period)
        context["statement"] = reporting.balance_sheet(period) if period else None
        return render(request, self.template_name, context)


class CashFlowView(_ReportBaseView):
    """Cash Flow Statement for an entity period."""

    template_name = "app_report/cash_flow.html"

    def get(self, request, *args, **kwargs):
        entity, periods, period = self._resolve(kwargs["entity_pk"])
        context = self._base_context(entity, periods, period)
        context["statement"] = reporting.cash_flow(period) if period else None
        return render(request, self.template_name, context)


class EquityStatementView(_ReportBaseView):
    """Statement of Changes in Equity for an entity period."""

    template_name = "app_report/equity_statement.html"

    def get(self, request, *args, **kwargs):
        entity, periods, period = self._resolve(kwargs["entity_pk"])
        context = self._base_context(entity, periods, period)
        context["statement"] = reporting.equity(period) if period else None
        return render(request, self.template_name, context)
