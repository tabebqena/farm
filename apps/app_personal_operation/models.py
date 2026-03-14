from typing import List

from django.core.exceptions import ValidationError
from django.db import models

from apps.app_base.mixins import (
    AdjustableMixin,
    AmountCleanMixin,
    Has2FundsMixin,
    HasLinkedTransactionMixin,
    ImmutableMixin,
)
from django.db.models import Sum, Q

from apps.app_base.models import BaseModel, ReversableModel
from apps.app_transaction.models import Transaction, TransactionType


class OperationType(models.TextChoices):
    CASH_INJECTION = "CASH_INJECTION", "Cash Injection"
    CASH_WITHDRAWAL = "CASH_WITHDRAWAL", "Cash Withdrawal"
    PROJECT_FUNDING = "PROJECT_FUNDING", "Project Funding"
    PROJECT_REFUND = "PROJECT_REFUND", "Project Refund"
    PROFIT_DISTRIBUTION = "PROFIT_DISTRIBUTION", "Profit Distribution"
    LOSS_COVERAGE = "LOSS_COVERAGE", "Loss Coverage"
    INTERNAL_TRANSFER = "INTERNAL_TRANSFER", "Internal Transfer"
    LOAN = "LOAN", "Loan"
    # LOAN_PAYMENT = "LOAN_PAYMENT", "Loan Payment"
    # LOAN_REPAYMENT = "LOAN_REPAYMENT", "Loan Repayment"


class Operation(
    ImmutableMixin,
    AdjustableMixin,
    AmountCleanMixin,
    HasLinkedTransactionMixin,
    Has2FundsMixin,
    ReversableModel,
    BaseModel,
):
    _immutable_fields = {"source": {}, "destination": {}, "amount": {}}
    _amount_name = "amount"
    _adjustments_related_name = "adjustments"
    # _max_payment_transaction_count = 1
    # _is_one_shot_operation = True

    source = models.ForeignKey(
        to="app_entity.Entity",
        on_delete=models.PROTECT,
        related_name="operations_outgoing",
    )

    destination = models.ForeignKey(
        "app_entity.Entity",
        on_delete=models.PROTECT,
        related_name="operations_incoming",
    )

    amount = models.DecimalField(max_digits=20, decimal_places=2)
    operation_type = models.CharField(max_length=30, choices=OperationType.choices)
    date = models.DateField()
    description = models.TextField(blank=True)
    officer = models.ForeignKey(
        "app_entity.Entity",
        on_delete=models.PROTECT,
        related_name="operations_supervised",
    )

    class Meta:
        verbose_name = "Operation"
        verbose_name_plural = "Operations"
        ordering = ["-date", "-created_at"]

    @property
    def owner(self):
        if self.operation_type in [
            OperationType.CASH_INJECTION,
            # self.OperationType.CASH_WITHDRAWAL,
            # self.OperationType.PROJECT_FUNDING,
            OperationType.PROJECT_REFUND,
            OperationType.PROFIT_DISTRIBUTION,
            # OperationType.LOSS_COVERAGE,
            # self.OperationType.INTERNAL_TRANSFER,
            # self.OperationType.DEBT_ISSUANCE,
            # self.OperationType.DEBT_PAYMENT,
            # OperationType.LOAN_REPAYMENT,
        ]:
            return self.destination
        return self.source

    @property
    def payment_source_fund(self):
        return self.source.fund

    @property
    def payment_target_fund(self):
        return self.destination.fund

    @property
    def _max_payment_transaction_count(self):
        # if self.operation_type == OperationType.LOAN_REPAYMENT:
        #     return -1
        return 1

    @property
    def _issuance_transaction_type(self):
        """Dynamic mapping based on operation type"""
        mapping = {
            OperationType.CASH_INJECTION: TransactionType.CAPITAL_INJECTION_ISSUANCE,
            OperationType.CASH_WITHDRAWAL: TransactionType.CAPITAL_WITHDRAWAL_ISSUANCE,
            OperationType.PROJECT_FUNDING: TransactionType.PROJECT_FUNDING_ISSUANCE,
            OperationType.PROJECT_REFUND: TransactionType.PROJECT_REFUND_ISSUANC,
            OperationType.PROFIT_DISTRIBUTION: TransactionType.PROFIT_DISTRIBUTION_ISSUANCE,
            OperationType.LOSS_COVERAGE: TransactionType.LOSS_COVERAGE_ISSUANCE,
            OperationType.INTERNAL_TRANSFER: TransactionType.INTERNAL_TRANSFER_ISSUANCE,
            OperationType.LOAN: TransactionType.LOAN_ISSUANCE,
            #
        }
        return mapping.get(self.operation_type)

    @property
    def _payment_transaction_type(self):
        """Dynamic mapping for the payment leg"""
        mapping = {
            OperationType.CASH_INJECTION: TransactionType.CAPITAL_INJECTION_PAYMENT,
            OperationType.CASH_WITHDRAWAL: TransactionType.CAPITAL_WITHDRAWAL_PAYMENT,
            OperationType.PROJECT_FUNDING: TransactionType.PROJECT_FUNDING_PAYMENT,
            OperationType.PROJECT_REFUND: TransactionType.PROJECT_REFUND_ISSUANC,
            OperationType.PROFIT_DISTRIBUTION: TransactionType.PROFIT_DISTRIBUTION_PAYMENT,
            OperationType.LOSS_COVERAGE: TransactionType.LOSS_COVERAGE_PAYMENT,
            OperationType.INTERNAL_TRANSFER: TransactionType.INTERNAL_TRANSFER_PAYMENT,
            OperationType.LOAN: TransactionType.LOAN_PAYMENT,
            # OperationType.LOAN_REPAYMENT: TransactionType.LOAN_PAYMENT,
        }
        return mapping.get(self.operation_type)

    @property
    def _implicit_reversable_transaction_types(self):
        rv = []
        issuance = self._issuance_transaction_type
        if issuance:
            rv.append(issuance)
        payment = self._payment_transaction_type
        if payment:
            rv.append(payment)
        print("_implicit_reversable_transaction_types", rv)
        return rv

    @property
    def _reversable_transaction_types(self) -> List[TransactionType]:
        rv = []
        issuance = self._issuance_transaction_type
        if issuance:
            rv.append(issuance)
        payment_type: "TransactionType" = self._payment_transaction_type
        if payment_type:
            rv.append(payment_type)
        return rv

    @property
    def _is_one_shot_operation(self):
        # if self.operation_type == OperationType.LOAN_REPAYMENT:
        #     return False
        return True

    def get_cash_flow_balance(self):
        """
        Calculates the net cash balance of an operation.
        Logic: (Cash Out / Payment) - (Cash In / Repayment)
        """
        # 1. Get all valid (non-reversed) transactions
        valid_txs = Transaction.objects.filter(
            object_id=self.pk,
            reversal_of__isnull=True,  # Is not a reversal
            reversed_by__isnull=True,  # Has not been reversed
        )

        # 2. Identify the Payment Leg (The initial cash outflow)
        payment_type = self._payment_transaction_type

        # 3. Filter for Payments and Repayments
        # We include the specific Payment type OR any transaction tagged as a repayment
        cash_movements = valid_txs.filter(
            Q(type=payment_type) | Q(type=TransactionType.LOAN_REPAYMENT)
        )

        # 4. Calculate Net Balance
        # We treat initial payment as negative (outflow) and repayment as positive (inflow)
        # Note: Adjust logic if your 'amount' is always positive
        total_payment = (
            cash_movements.filter(type=payment_type).aggregate(Sum("amount"))[
                "amount__sum"
            ]
            or 0
        )
        total_repayment = (
            cash_movements.filter(type=TransactionType.LOAN_REPAYMENT).aggregate(
                Sum("amount")
            )["amount__sum"]
            or 0
        )

        return total_payment - total_repayment

    def clean_source(self, **kwargs):
        if self.operation_type == OperationType.CASH_INJECTION:
            if not self.source.is_world:
                raise ValidationError("Injections source must be the World.")

    def clean_destination(self, **kwargs):
        if self.operation_type == OperationType.CASH_INJECTION:
            if not self.destination.person:
                raise ValidationError("Injections must target a Person.")

    def clean(self):
        # if self.operation_type == OperationType.CASH_INJECTION:
        #     if not self.destination.person:
        #         raise ValidationError("Injections must target a Person.")
        #     if not self.source.is_world:
        #         raise ValidationError("Injections source must be the World.")

        # # 1. Validate based on Operation Type
        # if self.operation_type == OperationType.PROJECT_FUNDING:
        #     if not self.destination.is_project:
        #         raise ValidationError("Project Funding must target a Project entity.")

        # 2. Debt Logic
        # if self.operation_type in [
        #     OperationType.DEBT_ISSUANCE,
        #     OperationType.DEBT_REPAYMENT,
        # ]:
        #     # Ensure an 'Interest Rate' or 'Due Date' exists if those fields are added
        #     pass
        return super().clean()

    def __str__(self):
        return f"Operation: {self.amount} from {self.source} to {self.destination}"
