from datetime import date

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from apps.app_base.logging_utils import logger
from apps.app_base.navigation import set_entity_navigation
from apps.app_entity.models import Entity
from apps.app_operation.models.period import FinancialPeriod
from farm.shortcuts import get_object_or_404

from . import reporting


def _resolve(request, entity_pk):
    """Load the entity, its periods, and the selected/default period."""
    logger.debug(f"Resolving report scope | entity_pk={entity_pk}")
    entity = get_object_or_404(
        Entity,
        pk=entity_pk,
        error_message="Entity not found or has been deleted.",
    )
    periods = list(entity.financial_periods.all().order_by("-start_date"))
    period_pk = request.GET.get("period")
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


def _base_context(request, entity, periods, period):
    set_entity_navigation(request, entity)
    return {
        "entity": entity,
        "periods": periods,
        "period": period,
        "today": date.today(),
        "currency": getattr(settings, "CURRENCY_SYMBOL", "$"),
    }


@login_required
def reports_hub_view(request, entity_pk):
    """Financial Reports hub for an entity."""
    entity, periods, period = _resolve(request, entity_pk)
    context = _base_context(request, entity, periods, period)
    return render(request, "app_report/report_hub.html", context)


@login_required
def income_statement_view(request, entity_pk):
    """Income Statement (P&L) for a project period."""
    entity, periods, period = _resolve(request, entity_pk)
    if not entity.is_project:
        raise PermissionDenied(
            "The Income Statement is only available for project entities."
        )
    context = _base_context(request, entity, periods, period)
    context["statement"] = reporting.income_statement(period) if period else None
    return render(request, "app_report/income_statement.html", context)


@login_required
def balance_sheet_view(request, entity_pk):
    """Balance Sheet for a project period."""
    entity, periods, period = _resolve(request, entity_pk)
    if not entity.is_project:
        raise PermissionDenied(
            "The Balance Sheet is only available for project entities."
        )
    context = _base_context(request, entity, periods, period)
    context["statement"] = reporting.balance_sheet(period) if period else None
    return render(request, "app_report/balance_sheet.html", context)


@login_required
def cash_flow_view(request, entity_pk):
    """Cash Flow Statement for an entity period."""
    entity, periods, period = _resolve(request, entity_pk)
    context = _base_context(request, entity, periods, period)
    context["statement"] = reporting.cash_flow(period) if period else None
    return render(request, "app_report/cash_flow.html", context)


@login_required
def equity_statement_view(request, entity_pk):
    """Statement of Changes in Equity for an entity period."""
    entity, periods, period = _resolve(request, entity_pk)
    context = _base_context(request, entity, periods, period)
    context["statement"] = reporting.equity(period) if period else None
    return render(request, "app_report/equity_statement.html", context)
