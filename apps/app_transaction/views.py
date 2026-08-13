import traceback
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.app_base.debug import DebugContext, debug_view
from apps.app_entity.models import Entity
from apps.app_transaction.models import Transaction
from apps.app_transaction.transaction_type import TransactionType
from farm.shortcuts import get_object_or_404


@debug_view
def entity_payment_transactions_view(request, entity_pk):
    """List all payment transactions related to an entity for balance tracking.

    Shows actual cash-flow (payment) transactions where the entity is either
    the source (outgoing) or the target (incoming). A running balance is
    computed for each row so the page can be used to track the fund balance
    over time. Issuance transactions are excluded because they do not affect
    the fund balance.
    """
    with DebugContext.section("Fetching entity transactions", {
        "entity_pk": entity_pk,
        "user": request.user.username,
    }):
        entity = get_object_or_404(
            Entity,
            pk=entity_pk,
            error_message="Entity not found or has been deleted.",
        )
        DebugContext.success("Entity loaded", {
            "entity_id": entity.id,
            "entity_type": entity.entity_type,
            "entity_name": entity.name,
        })

        transactions = (
            Transaction.objects.filter(
                Q(source=entity) | Q(target=entity),
                type__in=TransactionType.payment_types(),
                deleted_at__isnull=True,
            )
            .select_related("source", "target", "officer")
            .order_by("date", "pk")
        )

        # Annotate each transaction with its direction relative to this entity
        # and compute a running balance (incoming increases, outgoing decreases).
        running_balance = Decimal("0.00")
        total_incoming = Decimal("0.00")
        total_outgoing = Decimal("0.00")
        annotated_transactions = []
        for tx in transactions:
            if tx.target == entity:
                tx.direction = "incoming"
                running_balance += tx.amount
                total_incoming += tx.amount
            else:
                tx.direction = "outgoing"
                running_balance -= tx.amount
                total_outgoing += tx.amount
            tx.running_balance = running_balance
            annotated_transactions.append(tx)

        DebugContext.success("Transactions loaded", {
            "count": len(annotated_transactions),
            "total_incoming": str(total_incoming),
            "total_outgoing": str(total_outgoing),
            "running_balance": str(running_balance),
        })

    # Paginate the annotated list (running balance is computed over ALL rows
    # first, so it remains correct across pages).
    paginator = Paginator(annotated_transactions, 25)
    page_number = request.GET.get("page", 1)
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    # Replace the ambiguous "Entity" navigation label with the entity's display name
    if entity.entity_type in ("system", "world"):
        request.navigation_overrides = {"related_urls": {"Entity": None}}
    else:
        request.navigation_overrides = {
            "related_urls": {
                "Entity": {
                    "title": entity.get_display_name(),
                    "url": reverse("entity_detail", kwargs={"pk": entity.pk}),
                },
            }
        }

    context = {
        "entity": entity,
        "transactions": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "currency": getattr(settings, "CURRENCY_SYMBOL", "$"),
        "total_incoming": total_incoming,
        "total_outgoing": total_outgoing,
        "current_balance": entity.balance,
    }
    return render(request, "app_transaction/entity_payment_transactions.html", context)


def _build_obligation_transactions(
    entity,
    increase_source_types,
    decrease_source_types,
    increase_target_types,
    decrease_target_types,
):
    """
    Annotate the transactions that increase or decrease an entity's outstanding
    obligation (payables or receivables) and compute a running balance.

    Each returned transaction gets:
      - ``direction``: ``"increase"`` or ``"decrease"`` relative to the obligation
      - ``running_balance``: the cumulative obligation after this transaction

    Returns a tuple ``(annotated_transactions, total_increase, total_decrease)``.
    """
    transactions = (
        Transaction.objects.filter(
            Q(source=entity, type__in=increase_source_types + decrease_source_types)
            | Q(
                target=entity,
                type__in=increase_target_types + decrease_target_types,
            ),
            deleted_at__isnull=True,
        )
        .select_related("source", "target", "officer")
        .order_by("date", "pk")
    )

    # Match Entity.payables_at()/receivables_at(): exclude transactions already
    # reversed as of today (or reversed after today — still counted today) and
    # exclude reversal (mirror) transactions — they are not obligations and
    # their swapped source/target role would otherwise be miscounted.
    transactions = transactions.filter(
        reversal_of__isnull=True,
    ).filter(
        Q(reversed_by__isnull=True) | Q(reversed_by__date__date__gt=date.today())
    )

    running_balance = Decimal("0.00")
    total_increase = Decimal("0.00")
    total_decrease = Decimal("0.00")
    annotated_transactions = []
    for tx in transactions:
        if tx.source == entity and tx.type in increase_source_types:
            tx.direction = "increase"
            running_balance += tx.amount
            total_increase += tx.amount
        elif tx.target == entity and tx.type in increase_target_types:
            tx.direction = "increase"
            running_balance += tx.amount
            total_increase += tx.amount
        else:
            tx.direction = "decrease"
            running_balance -= tx.amount
            total_decrease += tx.amount
        tx.running_balance = running_balance
        annotated_transactions.append(tx)

    return annotated_transactions, total_increase, total_decrease


def _obligation_context(request, entity_pk, kind, template):
    """
    Build and render the paginated context for an obligation page
    (``kind`` is either ``"payables"`` or ``"receivables"``).
    """
    with DebugContext.section(f"Fetching entity {kind}", {
        "entity_pk": entity_pk,
        "user": request.user.username,
    }):
        entity = get_object_or_404(
            Entity,
            pk=entity_pk,
            error_message="Entity not found or has been deleted.",
        )
        DebugContext.success("Entity loaded", {
            "entity_id": entity.id,
            "entity_type": entity.entity_type,
            "entity_name": entity.name,
        })

        T = TransactionType
        if kind == "payables":
            increase_source_types = [
                T.PURCHASE_ISSUANCE,
                T.PURCHASE_ADJUSTMENT_INCREASE,
                T.SALE_ISSUANCE,
                T.SALE_ADJUSTMENT_INCREASE,
                T.EXPENSE_ISSUANCE,
                T.EXPENSE_ADJUSTMENT_INCREASE,
                T.PROJECT_REFUND_ISSUANCE,
            ]
            decrease_source_types = [
                T.PURCHASE_PAYMENT,
                T.SALE_COLLECTION,
                T.EXPENSE_PAYMENT,
                T.WORKER_ADVANCE_REPAYMENT,
                T.LOAN_REPAYMENT,
                T.PROJECT_REFUND_PAYMENT,
            ]
            increase_target_types = [T.WORKER_ADVANCE_PAYMENT, T.LOAN_PAYMENT]
            decrease_target_types = [
                T.PURCHASE_ADJUSTMENT_DECREASE,
                T.SALE_ADJUSTMENT_DECREASE,
                T.EXPENSE_ADJUSTMENT_DECREASE,
            ]
        else:  # receivables
            increase_source_types = [T.WORKER_ADVANCE_PAYMENT, T.LOAN_PAYMENT]
            decrease_source_types = [
                T.PURCHASE_ADJUSTMENT_DECREASE,
                T.SALE_ADJUSTMENT_DECREASE,
                T.EXPENSE_ADJUSTMENT_DECREASE,
            ]
            increase_target_types = [
                T.PURCHASE_ISSUANCE,
                T.PURCHASE_ADJUSTMENT_INCREASE,
                T.SALE_ISSUANCE,
                T.SALE_ADJUSTMENT_INCREASE,
                T.EXPENSE_ISSUANCE,
                T.EXPENSE_ADJUSTMENT_INCREASE,
                T.PROJECT_REFUND_ISSUANCE,
            ]
            decrease_target_types = [
                T.PURCHASE_PAYMENT,
                T.SALE_COLLECTION,
                T.EXPENSE_PAYMENT,
                T.WORKER_ADVANCE_REPAYMENT,
                T.LOAN_REPAYMENT,
                T.PROJECT_REFUND_PAYMENT,
            ]

        annotated_transactions, total_increase, total_decrease = (
            _build_obligation_transactions(
                entity,
                increase_source_types,
                decrease_source_types,
                increase_target_types,
                decrease_target_types,
            )
        )

        DebugContext.success(f"{kind} transactions loaded", {
            "count": len(annotated_transactions),
            "total_increase": str(total_increase),
            "total_decrease": str(total_decrease),
            "running_balance": str(total_increase - total_decrease),
        })

    # Paginate the annotated list (running balance is computed over ALL rows
    # first, so it remains correct across pages).
    paginator = Paginator(annotated_transactions, 25)
    page_number = request.GET.get("page", 1)
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    request.navigation_overrides = {
        "related_urls": {
            "Entity": {
                "title": entity.get_display_name(),
                "url": reverse("entity_detail", kwargs={"pk": entity.pk}),
            },
        }
    }

    context = {
        "entity": entity,
        "transactions": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "currency": getattr(settings, "CURRENCY_SYMBOL", "$"),
        "total_increase": total_increase,
        "total_decrease": total_decrease,
        "current_obligation": total_increase - total_decrease,
    }
    return render(request, template, context)


@debug_view
def entity_payables_view(request, entity_pk):
    """List transactions that contribute to an entity's outstanding payables.

    Payables are the obligations the entity owes (issuance/adjustment records)
    reduced by the payments/collections that settle them. Each row is annotated
    with whether it increases or decreases payables, plus a running payable
    balance so the page can be used to track payables over time.
    """
    return _obligation_context(
        request, entity_pk, "payables", "app_transaction/entity_payables.html"
    )


@debug_view
def entity_receivables_view(request, entity_pk):
    """List transactions that contribute to an entity's outstanding receivables.

    Receivables are the amounts owed to the entity (issuance/adjustment records)
    reduced by the collections/payments that settle them. Each row is annotated
    with whether it increases or decreases receivables, plus a running receivable
    balance so the page can be used to track receivables over time.
    """
    return _obligation_context(
        request, entity_pk, "receivables", "app_transaction/entity_receivables.html"
    )


@debug_view
def transaction_detail_view(request, transaction_pk):
    """Display a single transaction's details.

    The transaction list links here instead of offering a one-click reverse
    button, so a reversal cannot be triggered accidentally from the list. The
    user opens this detail page and, when appropriate, reverses from here.
    """
    with DebugContext.section("Fetching transaction details", {
        "transaction_pk": transaction_pk,
        "user": request.user.username,
    }):
        transaction = get_object_or_404(
            Transaction,
            pk=transaction_pk,
            deleted_at__isnull=True,
            error_message="Transaction not found or has been deleted.",
        )
        DebugContext.success("Transaction loaded", {
            "transaction_pk": transaction.pk,
            "type": transaction.type,
            "amount": float(transaction.amount),
            "source": str(transaction.source),
            "target": str(transaction.target),
            "is_reversed": transaction.is_reversed,
            "is_reversal": transaction.is_reversal,
            "object_id": transaction.object_id,
        })

    context = {
        "transaction": transaction,
        "can_reverse": not transaction.is_reversed and not transaction.is_reversal,
        "currency": getattr(settings, "CURRENCY_SYMBOL", "$"),
    }
    return render(request, "app_transaction/transaction_detail.html", context)


@debug_view
def transaction_reverse_view(request, pk):
    """Reverse an individual financial transaction (critical audit operation).

    This operates at the Transaction level — unlike operation-level reversal
    which reverses the entire operation including all its transactions, this
    view reverses a single transaction by swapping its source and target
    (creating a mirror-image reversal transaction).
    """
    with DebugContext.section("Fetching transaction for reversal", {
        "transaction_pk": pk,
        "user": request.user.username,
    }):
        transaction = Transaction.objects.filter(pk=pk).first()
        if not transaction:
            DebugContext.error("Transaction not found", None, {
                "transaction_pk": pk,
            })
            messages.error(request, "Transaction not found.")
            return redirect("home")

        DebugContext.success("Transaction loaded", {
            "transaction_pk": transaction.pk,
            "type": transaction.type,
            "amount": float(transaction.amount),
            "source": str(transaction.source),
            "target": str(transaction.target),
            "is_reversed": transaction.is_reversed,
            "is_reversal": transaction.is_reversal,
        })

    # Safety checks for reversibility
    if transaction.is_reversed:
        error_msg = "This transaction has already been reversed."
        DebugContext.warn(error_msg, {"transaction_pk": transaction.pk})
        DebugContext.audit(
            action="reversal_attempt_already_reversed",
            entity_type="Transaction",
            entity_id=transaction.pk,
            details={"reason": "already_reversed"},
            user=request.user.username,
        )
        messages.warning(request, error_msg)
        return redirect("operation_detail_view", pk=transaction.object_id)

    if transaction.is_reversal:
        error_msg = "This transaction is a reversal (You can't reverse it)."
        DebugContext.warn(error_msg, {"transaction_pk": transaction.pk})
        DebugContext.audit(
            action="reversal_attempt_on_reversal",
            entity_type="Transaction",
            entity_id=transaction.pk,
            details={"reason": "is_itself_reversal"},
            user=request.user.username,
        )
        messages.warning(request, error_msg)
        return redirect("operation_detail_view", pk=transaction.object_id)

    # Block reversing transactions that belong to one-shot operations.
    # One-shot operations (e.g. CashInjection, Birth, CapitalGain/Loss, etc.)
    # handle all their transactions implicitly during operation-level reversal.
    # Allowing manual transaction reversal would break consistency for these.
    operation = transaction.document
    if operation and getattr(operation, "_is_one_shot_operation", False):
        error_msg = (
            "This transaction belongs to a one-shot operation and cannot be "
            "reversed individually. Reverse the entire operation instead."
        )
        DebugContext.warn(error_msg, {
            "transaction_pk": transaction.pk,
            "operation_pk": operation.pk,
            "operation_type": operation.operation_type,
        })
        DebugContext.audit(
            action="reversal_attempt_on_one_shot_operation",
            entity_type="Transaction",
            entity_id=transaction.pk,
            details={
                "reason": "one_shot_operation",
                "operation_pk": operation.pk,
                "operation_type": operation.operation_type,
            },
            user=request.user.username,
        )
        messages.warning(request, error_msg)
        return redirect("operation_detail_view", pk=transaction.object_id)

    if request.method == "POST":
        with DebugContext.section("Processing transaction reversal", {
            "transaction_pk": transaction.pk,
            "type": transaction.type,
            "officer": request.user.username,
        }):
            reason = request.POST.get("reversal_reason", "").strip()

            if not reason:
                error_msg = "A reason for reversal is required."
                DebugContext.warn(error_msg, {"transaction_pk": transaction.pk})
                DebugContext.audit(
                    action="reversal_attempt_no_reason",
                    entity_type="Transaction",
                    entity_id=transaction.pk,
                    details={"reason": "missing_reversal_reason"},
                    user=request.user.username,
                )
                messages.error(request, error_msg)
            else:
                try:
                    with DebugContext.section("Executing transaction reversal"):
                        officer = request.user
                        reversal = transaction.reverse(
                            officer=officer,
                            reason=reason,
                        )

                    DebugContext.success("Transaction reversed successfully", {
                        "transaction_pk": transaction.pk,
                        "reversal_pk": reversal.pk,
                        "reason": reason[:100],
                    })
                    DebugContext.audit(
                        action="transaction_reversed",
                        entity_type="Transaction",
                        entity_id=transaction.pk,
                        details={
                            "reversal_pk": reversal.pk,
                            "type": transaction.type,
                            "amount": float(transaction.amount),
                            "reason": reason,
                            "officer": request.user.username,
                        },
                        user=request.user.username,
                    )

                    messages.success(
                        request,
                        f"Transaction #{transaction.pk} reversed successfully.",
                    )
                    return redirect("operation_detail_view", pk=transaction.object_id)
                except Exception as e:
                    error_details = {
                        "exception_type": type(e).__name__,
                        "error_message": str(e),
                        "transaction_pk": transaction.pk,
                        "officer": request.user.username,
                        "traceback": traceback.format_exc(),
                    }
                    DebugContext.error(
                        "Transaction reversal failed", e, data=error_details
                    )
                    DebugContext.audit(
                        action="transaction_reversal_failed",
                        entity_type="Transaction",
                        entity_id=transaction.pk,
                        details=error_details,
                        user=request.user.username,
                    )
                    traceback.print_exc()
                    messages.error(request, f"Reversal failed: {str(e)}")

    context = {
        "transaction": transaction,
        "today": timezone.now(),
    }
    return render(request, "app_transaction/reverse_form.html", context)
