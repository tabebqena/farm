import traceback
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.app_base.debug import DebugContext, debug_view
from apps.app_entity.models import Entity
from apps.app_transaction.models import Transaction
from apps.app_transaction.transaction_type import TransactionType
from farm.shortcuts import get_object_or_404


@debug_view
def entity_transactions_view(request, entity_pk):
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
    return render(request, "app_transaction/entity_transactions.html", context)


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
