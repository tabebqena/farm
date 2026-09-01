from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from apps.app_base.logging_utils import audit_logger, logger
from apps.app_base.navigation import set_entity_navigation
from apps.app_entity.models import Entity
from apps.app_operation.models.period import FinancialPeriod
from apps.app_transaction.running_balance import running_balance_rows
from farm.shortcuts import get_object_or_404


@login_required
def period_detail_view(request, period_pk):
    """View financial period details."""
    logger.debug(
        f"Fetching financial period | period_pk={period_pk} | "
        f"user={request.user.username}"
    )
    period = get_object_or_404(
        FinancialPeriod,
        pk=period_pk,
        error_message="Financial period not found or has been deleted.",
    )
    logger.debug(
        f"Period loaded | period_id={period.pk} | entity_id={period.entity.pk} | "
        f"start_date={period.start_date} | end_date={period.end_date}"
    )
    context = {
        "period": period,
        "entity": period.entity,
    }
    return render(
        request,
        "app_operation/period_detail.html",
        context,
    )


@login_required
def period_list_view(request, entity_pk):
    """List all financial periods for an entity."""
    logger.debug(
        f"Fetching entity and periods | entity_pk={entity_pk} | "
        f"user={request.user.username}"
    )
    entity = get_object_or_404(
        Entity, pk=entity_pk, error_message="Entity not found or has been deleted."
    )
    all_periods = entity.financial_periods.all().order_by("-start_date")
    logger.debug(
        f"Periods loaded | entity_id={entity.pk} | period_count={all_periods.count()}"
    )

    paginator = Paginator(all_periods, 25)
    page_number = request.GET.get("page", 1)
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    # Replace the ambiguous "Entity" navigation label with the entity's display name
    set_entity_navigation(request, entity)

    context = {
        "entity": entity,
        "periods": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
    }
    return render(request, "app_operation/period_list.html", context)


@login_required
def period_close_view(request, period_pk):
    """Close a financial period."""
    logger.debug(
        f"Fetching period for closing | period_pk={period_pk} | "
        f"user={request.user.username}"
    )
    period = get_object_or_404(
        FinancialPeriod,
        pk=period_pk,
        error_message="Financial period not found or has been deleted.",
    )
    logger.debug(
        f"Period loaded | period_id={period.pk} | "
        f"start_date={period.start_date} | "
        f"end_date={period.end_date if period.end_date else None}"
    )

    if not period.can_close:
        error_msg = _("This period is already closed.")
        logger.warning(f"Close attempt on already closed period | period_id={period.pk}")
        audit_logger.info(
            f"period_close_attempt_on_closed | FinancialPeriod:{period.pk} | "
            f"user={request.user.username} | reason=period_already_closed"
        )
        context = {
            "period": period,
            "errors": [error_msg],
        }
        return render(request, "app_operation/period_close.html", context, status=400)

    if request.method == "GET":
        warnings = period.closure_warnings()

        context = {
            "period": period,
            "today": date.today(),
            "warnings": warnings,
        }
        return render(request, "app_operation/period_close.html", context)

    if request.method == "POST":
        logger.debug(
            f"Processing period closure | period_pk={period_pk} | "
            f"user={request.user.username}"
        )
        try:
            end_date_str = request.POST.get("end_date")
            if not end_date_str:
                raise ValidationError(_("End date is required."))

            end_date = date.fromisoformat(end_date_str)

            with transaction.atomic():
                logger.debug(f"Closing period | end_date={end_date}")
                period.close(end_date)
                logger.debug(
                    f"Period closed successfully | period_id={period.pk} | "
                    f"end_date={period.end_date}"
                )
                audit_logger.info(
                    f"period_closed | FinancialPeriod:{period.pk} | "
                    f"user={request.user.username} | entity_id={period.entity.pk} | "
                    f"start_date={period.start_date} | end_date={period.end_date}"
                )
            return redirect("period_list_view", entity_pk=period.entity.pk)
        except ValidationError as e:
            error_details = {
                "validation_errors": str(e.messages),
                "period_id": period.pk,
            }
            logger.warning(f"Period closure validation failed | {error_details}")
            audit_logger.info(
                f"period_closure_validation_failed | FinancialPeriod:{period.pk} | "
                f"user={request.user.username} | {error_details}"
            )
            context = {"period": period, "errors": e.messages}
            return render(
                request, "app_operation/period_close.html", context, status=400
            )


@login_required
def period_ledger_view(request, period_pk):
    """Show running-balance cash ledger for a financial period."""
    from django.db.models import Q

    from apps.app_transaction.models import Transaction
    from apps.app_transaction.transaction_type import TransactionType

    logger.debug(f"Fetching period for ledger | period_pk={period_pk}")
    period = get_object_or_404(
        FinancialPeriod,
        pk=period_pk,
        error_message="Financial period not found.",
    )

    entity = period.entity
    date_q = Q(date__date__gte=period.start_date)
    if period.end_date:
        date_q &= Q(date__date__lt=period.end_date)

    raw_txs = (
        Transaction.objects.filter(
            Q(source=entity) | Q(target=entity),
            type__in=TransactionType.payment_types(),
        )
        .filter(date_q)
        .select_related("source", "target", "reversal_of")
        .prefetch_related("reversed_by")
        .order_by("date", "created_at")
    )

    # Direction: a transaction credited to the entity's fund adds to the
    # balance; one debited from it subtracts. The running balance starts at the
    # previous period's closing balance.
    rows, _total_in, _total_out = running_balance_rows(
        raw_txs,
        lambda tx: (
            ("credit", tx.amount)
            if tx.target_id == entity.pk
            else ("debit", -tx.amount)
        ),
        initial=period.previous_balance,
    )
    ledger_rows = [
        {
            "tx": tx,
            "direction": direction,
            "delta": delta,
            "balance": balance,
            "counterparty": tx.source if direction == "credit" else tx.target,
        }
        for tx, direction, delta, balance in rows
    ]
    closing_balance = rows[-1][3] if rows else period.previous_balance

    return render(
        request,
        "app_operation/period_ledger.html",
        {
            "period": period,
            "entity": entity,
            "opening_balance": period.previous_balance,
            "closing_balance": closing_balance,
            "ledger_rows": ledger_rows,
        },
    )
