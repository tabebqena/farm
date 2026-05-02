from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from apps.app_base.debug import DebugContext, debug_view
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity
from apps.app_operation.models.period import FinancialPeriod


@login_required
@debug_view
def period_detail_view(request, period_pk):
    """View financial period details."""
    with DebugContext.section(
        "Fetching financial period",
        {"period_pk": period_pk, "user": request.user.username},
    ):
        period = get_object_or_404(
            FinancialPeriod,
            pk=period_pk,
            error_message="Financial period not found or has been deleted.",
        )
        DebugContext.success(
            "Period loaded",
            {
                "period_id": period.pk,
                "entity_id": period.entity.pk,
                "start_date": str(period.start_date),
                "end_date": str(period.end_date),
            },
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
@debug_view
def period_list_view(request, entity_pk):
    """List all financial periods for an entity."""
    with DebugContext.section(
        "Fetching entity and periods",
        {"entity_pk": entity_pk, "user": request.user.username},
    ):
        entity = get_object_or_404(
            Entity, pk=entity_pk, error_message="Entity not found or has been deleted."
        )
        all_periods = entity.financial_periods.all().order_by("-start_date")
        DebugContext.success(
            "Periods loaded",
            {
                "entity_id": entity.pk,
                "period_count": all_periods.count(),
            },
        )

    paginator = Paginator(all_periods, 25)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = {
        "entity": entity,
        "periods": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
    }
    return render(request, "app_operation/period_list.html", context)


@login_required
@debug_view
def period_create_view(request, entity_pk):
    """Create a new financial period."""
    with DebugContext.section(
        "Fetching entity for period creation",
        {"entity_pk": entity_pk, "user": request.user.username},
    ):
        entity = get_object_or_404(
            Entity, pk=entity_pk, error_message="Entity not found or has been deleted."
        )
        DebugContext.success("Entity loaded", {"entity_id": entity.pk})

    if entity.active and entity.financial_periods.exists():
        error_msg = _(
            "New periods are created automatically when the current period is closed."
        )
        DebugContext.warn(
            "Manual period creation attempt for active entity with existing periods",
            {"entity_id": entity.pk},
        )
        DebugContext.audit(
            action="period_creation_blocked_for_active_entity",
            entity_type="Entity",
            entity_id=entity.pk,
            details={"reason": "active_entity_with_existing_periods"},
            user=request.user.username,
        )
        messages.error(request, error_msg)
        return redirect("period_list_view", entity_pk=entity.pk)

    if request.method == "GET":
        context = {"entity": entity}
        return render(
            request,
            "app_operation/period_form.html",
            context,
        )

    if request.method == "POST":
        with DebugContext.section(
            "Processing period creation",
            {
                "entity_pk": entity_pk,
                "user": request.user.username,
            },
        ):
            try:
                start_date = request.POST.get("start_date")
                if not start_date:
                    raise ValidationError(_("Start date is required."))

                with DebugContext.section(
                    "Creating financial period", {"start_date": start_date}
                ):
                    period = FinancialPeriod(entity=entity, start_date=start_date)
                    period.full_clean()
                    period.save()

                    DebugContext.success(
                        "Period created successfully",
                        {
                            "period_id": period.pk,
                            "start_date": str(period.start_date),
                        },
                    )
                    DebugContext.audit(
                        action="period_created",
                        entity_type="FinancialPeriod",
                        entity_id=period.pk,
                        details={
                            "entity_id": entity.pk,
                            "start_date": str(period.start_date),
                        },
                        user=request.user.username,
                    )
                return redirect("period_list_view", entity_pk=entity.pk)
            except ValidationError as e:
                error_details = {
                    "validation_errors": str(e.messages),
                    "entity_id": entity.pk,
                }
                DebugContext.warn("Period creation validation failed", error_details)
                DebugContext.audit(
                    action="period_creation_validation_failed",
                    entity_type="FinancialPeriod",
                    entity_id=None,
                    details=error_details,
                    user=request.user.username,
                )
                context = {"entity": entity, "errors": e.messages}
                return render(
                    request, "app_operation/period_form.html", context, status=400
                )


@login_required
@debug_view
def period_close_view(request, period_pk):
    """Close a financial period."""
    with DebugContext.section(
        "Fetching period for closing",
        {"period_pk": period_pk, "user": request.user.username},
    ):
        period = get_object_or_404(
            FinancialPeriod,
            pk=period_pk,
            error_message="Financial period not found or has been deleted.",
        )
        DebugContext.success(
            "Period loaded",
            {
                "period_id": period.pk,
                "start_date": str(period.start_date),
                "end_date": str(period.end_date) if period.end_date else None,
            },
        )

    if period.end_date is not None:
        error_msg = _("This period is already closed.")
        DebugContext.warn(
            "Close attempt on already closed period", {"period_id": period.pk}
        )
        DebugContext.audit(
            action="period_close_attempt_on_closed",
            entity_type="FinancialPeriod",
            entity_id=period.pk,
            details={"reason": "period_already_closed"},
            user=request.user.username,
        )
        context = {
            "period": period,
            "errors": [error_msg],
        }
        return render(request, "app_operation/period_close.html", context, status=400)

    if request.method == "GET":
        warnings = []

        if period.receivables > 0:
            warnings.append(
                _("Outstanding receivables: {amount}").format(
                    amount=period.receivables
                )
            )

        if period.payables > 0:
            warnings.append(
                _("Outstanding payables: {amount}").format(amount=period.payables)
            )

        if period.outstanding_loan_credited > 0:
            warnings.append(
                _("Outstanding loans given: {amount}").format(
                    amount=period.outstanding_loan_credited
                )
            )

        if period.outstanding_loan_received > 0:
            warnings.append(
                _("Outstanding loans received: {amount}").format(
                    amount=period.outstanding_loan_received
                )
            )

        if period.outstanding_worker_advance_paid > 0:
            warnings.append(
                _("Outstanding worker advances paid: {amount}").format(
                    amount=period.outstanding_worker_advance_paid
                )
            )

        if period.outstanding_worker_advance_received > 0:
            warnings.append(
                _("Outstanding worker advances received: {amount}").format(
                    amount=period.outstanding_worker_advance_received
                )
            )

        context = {
            "period": period,
            "today": date.today(),
            "warnings": warnings,
        }
        return render(request, "app_operation/period_close.html", context)

    if request.method == "POST":
        with DebugContext.section(
            "Processing period closure",
            {
                "period_pk": period_pk,
                "user": request.user.username,
            },
        ):
            try:
                end_date_str = request.POST.get("end_date")
                if not end_date_str:
                    raise ValidationError(_("End date is required."))

                end_date = date.fromisoformat(end_date_str)

                with transaction.atomic():
                    with DebugContext.section(
                        "Closing period", {"end_date": str(end_date)}
                    ):
                        period.close(end_date)
                        DebugContext.success(
                            "Period closed successfully",
                            {
                                "period_id": period.pk,
                                "end_date": str(period.end_date),
                            },
                        )
                        DebugContext.audit(
                            action="period_closed",
                            entity_type="FinancialPeriod",
                            entity_id=period.pk,
                            details={
                                "entity_id": period.entity.pk,
                                "start_date": str(period.start_date),
                                "end_date": str(period.end_date),
                            },
                            user=request.user.username,
                        )
                return redirect("period_list_view", entity_pk=period.entity.pk)
            except ValidationError as e:
                error_details = {
                    "validation_errors": str(e.messages),
                    "period_id": period.pk,
                }
                DebugContext.warn("Period closure validation failed", error_details)
                DebugContext.audit(
                    action="period_closure_validation_failed",
                    entity_type="FinancialPeriod",
                    entity_id=period.pk,
                    details=error_details,
                    user=request.user.username,
                )
                context = {"period": period, "errors": e.messages}
                return render(
                    request, "app_operation/period_close.html", context, status=400
                )


@login_required
@debug_view
def period_ledger_view(request, period_pk):
    """Show running-balance cash ledger for a financial period."""
    from django.db.models import Q
    from apps.app_transaction.models import Transaction
    from apps.app_transaction.transaction_type import TransactionType

    with DebugContext.section("Fetching period for ledger", {"period_pk": period_pk}):
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

    running = period.previous_balance
    ledger_rows = []
    for tx in raw_txs:
        if tx.target_id == entity.pk:
            direction, delta = "credit", tx.amount
        else:
            direction, delta = "debit", -tx.amount
        running += delta
        ledger_rows.append({
            "tx": tx,
            "direction": direction,
            "delta": tx.amount,
            "balance": running,
            "counterparty": tx.source if direction == "credit" else tx.target,
        })

    return render(request, "app_operation/period_ledger.html", {
        "period": period,
        "entity": entity,
        "opening_balance": period.previous_balance,
        "closing_balance": running,
        "ledger_rows": ledger_rows,
    })
