from datetime import date

from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View

from apps.app_base.logging_utils import audit_logger, logger
from apps.app_base.navigation import set_entity_navigation
from apps.app_base.reversal import request_reversal, reversal_guard_error
from apps.app_entity.models import Entity
from apps.app_transaction.models import Transaction
from apps.app_transaction.running_balance import running_balance_rows
from apps.app_transaction.transaction_type import TransactionType
from farm.shortcuts import get_object_or_404, paginate


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

    def _classify(tx):
        if tx.source == entity and tx.type in increase_source_types:
            return "increase", tx.amount
        if tx.target == entity and tx.type in increase_target_types:
            return "increase", tx.amount
        return "decrease", -tx.amount

    rows, total_increase, total_decrease = running_balance_rows(
        transactions, _classify
    )
    annotated_transactions = []
    for tx, direction, _delta, balance in rows:
        tx.direction = direction
        tx.running_balance = balance
        annotated_transactions.append(tx)

    return annotated_transactions, total_increase, total_decrease


class EntityPaymentTransactionsView(View):
    """List all payment transactions related to an entity for balance tracking.

    Shows actual cash-flow (payment) transactions where the entity is either
    the source (outgoing) or the target (incoming). A running balance is
    computed for each row so the page can be used to track the fund balance
    over time. Issuance transactions are excluded because they do not affect
    the fund balance.
    """

    def get(self, request, *args, **kwargs):
        entity_pk = kwargs["entity_pk"]
        logger.debug(
            f"Fetching entity transactions | entity_pk={entity_pk} | "
            f"user={request.user.username}"
        )
        entity = get_object_or_404(
            Entity,
            pk=entity_pk,
            error_message="Entity not found or has been deleted.",
        )
        logger.debug(
            f"Entity loaded | entity_id={entity.id} | entity_type={entity.entity_type} | "
            f"entity_name={entity.name}"
        )

        selected_type = request.GET.get("type", "").strip()
        transactions = (
            Transaction.objects.filter(
                Q(source=entity) | Q(target=entity),
                type__in=TransactionType.payment_types(),
                deleted_at__isnull=True,
            )
            .select_related("source", "target", "officer")
            .order_by("date", "pk")
        )
        if selected_type in TransactionType.values:
            transactions = transactions.filter(type=selected_type)

        # Annotate each transaction with its direction relative to this entity
        # and compute a running balance (incoming increases, outgoing decreases).
        rows, total_incoming, total_outgoing = running_balance_rows(
            transactions,
            lambda tx: (
                ("incoming", tx.amount)
                if tx.target == entity
                else ("outgoing", -tx.amount)
            ),
        )
        annotated_transactions = []
        for tx, direction, _delta, balance in rows:
            tx.direction = direction
            tx.running_balance = balance
            annotated_transactions.append(tx)

        logger.debug(
            f"Transactions loaded | count={len(annotated_transactions)} | "
            f"total_incoming={total_incoming} | total_outgoing={total_outgoing} | "
            f"running_balance={total_incoming - total_outgoing}"
        )

        # Paginate the annotated list (running balance is computed over ALL rows
        # first, so it remains correct across pages).
        page_obj, paginator = paginate(request, annotated_transactions)

        # Replace the ambiguous "Entity" navigation label with the entity's display name
        set_entity_navigation(request, entity)

        context = {
            "entity": entity,
            "transactions": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": paginator,
            "currency": getattr(settings, "CURRENCY_SYMBOL", "$"),
            "total_incoming": total_incoming,
            "total_outgoing": total_outgoing,
            "current_balance": entity.balance,
            "selected_type": selected_type,
        }
        return render(
            request, "app_transaction/entity_payment_transactions.html", context
        )


class _ObligationListView(View):
    """Shared plumbing for the entity payables/receivables list pages."""

    kind: str
    template_name: str

    def _obligation_context(self):
        """
        Build and render the paginated context for an obligation page
        (``self.kind`` is either ``"payables"`` or ``"receivables"``).
        """
        request = self.request
        entity_pk = self.kwargs["entity_pk"]
        kind = self.kind
        logger.debug(
            f"Fetching entity {kind} | entity_pk={entity_pk} | user={request.user.username}"
        )
        entity = get_object_or_404(
            Entity,
            pk=entity_pk,
            error_message="Entity not found or has been deleted.",
        )
        logger.debug(
            f"Entity loaded | entity_id={entity.id} | entity_type={entity.entity_type} | "
            f"entity_name={entity.name}"
        )

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

        logger.debug(
            f"{kind} transactions loaded | count={len(annotated_transactions)} | "
            f"total_increase={total_increase} | total_decrease={total_decrease} | "
            f"running_balance={total_increase - total_decrease}"
        )

        # Paginate the annotated list (running balance is computed over ALL rows
        # first, so it remains correct across pages).
        page_obj, paginator = paginate(request, annotated_transactions)

        set_entity_navigation(request, entity)

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
        return render(request, self.template_name, context)

    def get(self, request, *args, **kwargs):
        return self._obligation_context()


class EntityPayablesView(_ObligationListView):
    """List transactions that contribute to an entity's outstanding payables.

    Payables are the obligations the entity owes (issuance/adjustment records)
    reduced by the payments/collections that settle them. Each row is annotated
    with whether it increases or decreases payables, plus a running payable
    balance so the page can be used to track payables over time.
    """

    kind = "payables"
    template_name = "app_transaction/entity_payables.html"


class EntityReceivablesView(_ObligationListView):
    """List transactions that contribute to an entity's outstanding receivables.

    Receivables are the amounts owed to the entity (issuance/adjustment records)
    reduced by the collections/payments that settle them. Each row is annotated
    with whether it increases or decreases receivables, plus a running receivable
    balance so the page can be used to track receivables over time.
    """

    kind = "receivables"
    template_name = "app_transaction/entity_receivables.html"


class TransactionDetailView(View):
    """Display a single transaction's details.

    The transaction list links here instead of offering a one-click reverse
    button, so a reversal cannot be triggered accidentally from the list. The
    user opens this detail page and, when appropriate, reverses from here.
    """

    def get(self, request, *args, **kwargs):
        transaction_pk = kwargs["transaction_pk"]
        logger.debug(
            f"Fetching transaction details | transaction_pk={transaction_pk} | "
            f"user={request.user.username}"
        )
        transaction = get_object_or_404(
            Transaction,
            pk=transaction_pk,
            deleted_at__isnull=True,
            error_message="Transaction not found or has been deleted.",
        )
        logger.debug(
            f"Transaction loaded | transaction_pk={transaction.pk} | type={transaction.type} | "
            f"amount={float(transaction.amount)} | source={transaction.source} | "
            f"target={transaction.target} | is_reversed={transaction.is_reversed} | "
            f"is_reversal={transaction.is_reversal} | object_id={transaction.object_id}"
        )

        context = {
            "transaction": transaction,
            "can_reverse": not transaction.is_reversed and not transaction.is_reversal,
            "currency": getattr(settings, "CURRENCY_SYMBOL", "$"),
        }
        return render(request, "app_transaction/transaction_detail.html", context)


class TransactionReverseView(View):
    """Reverse an individual financial transaction (critical audit operation).

    This operates at the Transaction level — unlike operation-level reversal
    which reverses the entire operation including all its transactions, this
    view reverses a single transaction by swapping its source and target
    (creating a mirror-image reversal transaction).
    """

    def get(self, request, *args, **kwargs):
        return self._handle(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        return self._handle(request, *args, **kwargs)

    def _handle(self, request, *args, **kwargs):
        pk = kwargs["pk"]
        logger.debug(
            f"Fetching transaction for reversal | transaction_pk={pk} | "
            f"user={request.user.username}"
        )
        transaction = Transaction.objects.filter(pk=pk).first()
        if not transaction:
            logger.error(f"Transaction not found | transaction_pk={pk}")
            messages.error(request, "Transaction not found.")
            return redirect("home")

        logger.debug(
            f"Transaction loaded | transaction_pk={transaction.pk} | type={transaction.type} | "
            f"amount={float(transaction.amount)} | source={transaction.source} | "
            f"target={transaction.target} | is_reversed={transaction.is_reversed} | "
            f"is_reversal={transaction.is_reversal}"
        )

        # Safety checks for reversibility
        error_msg = reversal_guard_error(transaction, "transaction")
        if error_msg:
            if transaction.is_reversed:
                action = "reversal_attempt_already_reversed"
                details = {"reason": "already_reversed"}
            else:
                action = "reversal_attempt_on_reversal"
                details = {"reason": "is_itself_reversal"}
            logger.warning(f"{error_msg} | transaction_pk={transaction.pk}")
            audit_logger.info(
                f"{action} | Transaction:{transaction.pk} | "
                f"user={request.user.username} | {details}"
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
            logger.warning(
                f"{error_msg} | transaction_pk={transaction.pk} | "
                f"operation_pk={operation.pk} | operation_type={operation.operation_type}"
            )
            audit_logger.info(
                f"reversal_attempt_on_one_shot_operation | Transaction:{transaction.pk} | "
                f"user={request.user.username} | reason=one_shot_operation | "
                f"operation_pk={operation.pk} | operation_type={operation.operation_type}"
            )
            messages.warning(request, error_msg)
            return redirect("operation_detail_view", pk=transaction.object_id)

        if request.method == "POST":
            logger.debug(
                f"Processing transaction reversal | transaction_pk={transaction.pk} | "
                f"type={transaction.type} | officer={request.user.username}"
            )
            response = request_reversal(
                request,
                transaction,
                record_type="transaction",
                reverse_call=lambda officer, reason: transaction.reverse(
                    officer=officer, reason=reason
                ),
                audit_success=lambda request, obj, reason, reversal: (
                    f"transaction_reversed | Transaction:{obj.pk} | "
                    f"user={request.user.username} | reversal_pk={reversal.pk} | "
                    f"type={obj.type} | amount={float(obj.amount)} | "
                    f"reason={reason} | officer={request.user.username}"
                ),
                audit_failure=lambda request, obj, error, error_details: (
                    f"transaction_reversal_failed | Transaction:{obj.pk} | "
                    f"user={request.user.username} | error={error_details}"
                ),
                success_message=lambda request, obj, reason: (
                    f"Transaction #{obj.pk} reversed successfully."
                ),
                error_message=lambda error: f"Reversal failed: {str(error)}",
                redirect_to=lambda obj: redirect(
                    "operation_detail_view", pk=obj.object_id
                ),
                missing_reason_audit=lambda request, obj: (
                    f"reversal_attempt_no_reason | Transaction:{obj.pk} | "
                    f"user={request.user.username} | reason=missing_reversal_reason"
                ),
                error_details_extra=lambda obj: {"transaction_pk": obj.pk},
            )
            if response is not None:
                return response

        context = {
            "transaction": transaction,
            "today": timezone.now(),
        }
        return render(request, "app_transaction/reverse_form.html", context)
