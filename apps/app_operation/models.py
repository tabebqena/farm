import logging
from decimal import Decimal
from typing import List

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum

from apps.app_base.mixins import (
    AdjustableMixin,
    AmountCleanMixin,
    ImmutableMixin,
    LinkedIssuanceTransactionMixin,
    LinkedPaymentTransactionMixin,
    OfficerMixin,
)
from apps.app_base.models import BaseModel, ReversableModel
from apps.app_transaction.transaction_type import TransactionType

logger = logging.getLogger(__name__)

# class TrackingMode(models.TextChoices):
#     INDIVIDUAL = "INDIVIDUAL", "Individual (Tag ID)"
#     BATCH = "BATCH", "Batch/Group"
#     COMMODITY = "COMMODITY", "Quantity (Weight/Volume)"


# class Product(BaseModel):
#     ear_tag = models.CharField(max_length=255)
#     name = models.CharField(max_length=255)  # e.g. "Angus Cow #405" or "Batch #12"
#     category = models.ForeignKey(
#         SpendingCategory, on_delete=models.PROTECT
#     )  # e.g. "Cattle"
#     tracking_mode = models.CharField(choices=TrackingMode.choices)

#     # Livestock-specific fields
#     birth_date = models.DateField(null=True)
#     initial_weight = models.DecimalField(decimal_places=5, max_digits=24)

default_categories = {
    # Labor
    "Permanent Staff Salaries": {
        "type": "EXPENSE",
        "desc": "Labor & Personnel: Monthly wages",
    },
    "Casual/Daily Labor": {
        "type": "EXPENSE",
        "desc": "Labor & Personnel: One-off help",
    },
    "Security Services": {
        "type": "EXPENSE",
        "desc": "Labor & Personnel: Security fees",
    },
    # Professional
    "Veterinary Consultation": {
        "type": "EXPENSE",
        "desc": "Professional Services: Clinical fees",
    },
    "Breeding/AI Technical Fees": {
        "type": "EXPENSE",
        "desc": "Professional Services: AI fees",
    },
    "Shearing/Hoof Trimming": {
        "type": "EXPENSE",
        "desc": "Professional Services: Maintenance",
    },
    # Infrastructure
    "Electricity/Energy": {"type": "EXPENSE", "desc": "Utilities: Power & Heating"},
    "Water Access Fees": {"type": "EXPENSE", "desc": "Utilities: Pumping & Access"},
    "Machinery Servicing": {"type": "EXPENSE", "desc": "Utilities: Repairs labor"},
    # Purchases (Inventory)
    "Animal Feed Stock": {
        "type": "PURCHASE",
        "desc": "Inventory: Bulk feed & supplements",
    },
    "Medical Supplies": {"type": "PURCHASE", "desc": "Inventory: Vaccines & meds"},
    # Sales (Revenue)
    "Livestock Sales": {"type": "SALE", "desc": "Revenue: Sale of live animals"},
    "Milk/Dairy Sales": {"type": "SALE", "desc": "Revenue: Sale of dairy products"},
    # Land & Logistics
    "Land Lease/Rent": {"type": "EXPENSE", "desc": "Fixed: Grazing land lease"},
    "Animal Transport": {"type": "EXPENSE", "desc": "Logistics: Trucking services"},
    "Slaughter Fees": {"type": "EXPENSE", "desc": "Logistics: Abattoir service fees"},
}


class FinancialCategory(BaseModel):
    TYPE_CHOICES = [
        ("PURCHASE", "Purchase"),
        ("SALE", "Sale"),
        ("EXPENSE", "Expense"),
    ]

    name = models.CharField(max_length=100)
    parent_entity = models.ForeignKey(
        "app_entity.Entity", on_delete=models.CASCADE, related_name="categories"
    )

    category_type = models.CharField(
        max_length=20, choices=TYPE_CHOICES, default="EXPENSE"
    )

    max_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        # Prevents adding the same category name twice for the same parent
        unique_together = ("name", "parent_entity")
        verbose_name_plural = "Financial Categories"

    def __str__(self):
        return f"{self.name} ({self.category_type})"


class OperationType(models.TextChoices):
    CASH_INJECTION = "CASH_INJECTION", "Cash Injection"
    CASH_WITHDRAWAL = "CASH_WITHDRAWAL", "Cash Withdrawal"
    PROJECT_FUNDING = "PROJECT_FUNDING", "Project Funding"
    PROJECT_REFUND = "PROJECT_REFUND", "Project Refund"
    PROFIT_DISTRIBUTION = "PROFIT_DISTRIBUTION", "Profit Distribution"
    LOSS_COVERAGE = "LOSS_COVERAGE", "Loss Coverage"
    INTERNAL_TRANSFER = "INTERNAL_TRANSFER", "Internal Transfer"
    LOAN = "LOAN", "Loan"
    PURCHASE = "PURCHASE", "Purchase"
    SALE = "SALE", "Sale"
    EXPENSE = "EXPENSE", "EXPENSE"

    CAPITAL_GAIN = "CAPITAL_GAIN", "CAPITAL_GAIN"
    CAPITAL_LOSS = "CAPITAL_LOSS", "CAPITAL_LOSS"

    @staticmethod
    def get_canonical_type(url_str_type):
        return {
            "cash-injection": OperationType.CASH_INJECTION.value,
            "cash-withdrawal": OperationType.CASH_WITHDRAWAL.value,
            "project-funding": OperationType.PROJECT_FUNDING.value,
            "project-refunding": OperationType.PROJECT_REFUND.value,
            "profit-distribution": OperationType.PROFIT_DISTRIBUTION.value,
            "loss-coverage": OperationType.LOSS_COVERAGE.value,
            "internal-transfer": OperationType.INTERNAL_TRANSFER.value,
            "loan": OperationType.LOAN,
            "purchase": OperationType.PURCHASE,
            "expense": OperationType.EXPENSE.value,
            "capital-gain": OperationType.CAPITAL_GAIN.value,
            "capital-loss": OperationType.CAPITAL_LOSS.value,
        }.get(url_str_type, None)

    @staticmethod
    def _is_one_shot_operation(operation_type):
        if operation_type in [
            OperationType.PURCHASE,
            OperationType.SALE,
            OperationType.EXPENSE,
        ]:
            return False
        return True

    @staticmethod
    def has_repayments(operation_type):
        if operation_type == OperationType.LOAN:
            return True
        return False


class Operation(
    ImmutableMixin,
    AdjustableMixin,
    AmountCleanMixin,
    LinkedIssuanceTransactionMixin,
    LinkedPaymentTransactionMixin,
    OfficerMixin,
    ReversableModel,
    BaseModel,
):
    _immutable_fields = {"source": {}, "destination": {}, "amount": {}}
    _amount_name = "amount"
    _adjustments_related_name = "adjustments"

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
    def max_payment_transaction_count(self):
        if self.operation_type in [
            OperationType.PURCHASE,
            OperationType.SALE,
            OperationType.EXPENSE,
        ]:
            return -1
        return 1

    @property
    def _issuance_transaction_type(self):
        """Dynamic mapping based on operation type"""
        mapping = {
            OperationType.CASH_INJECTION: TransactionType.CAPITAL_INJECTION_ISSUANCE,
            OperationType.CASH_WITHDRAWAL: TransactionType.CAPITAL_WITHDRAWAL_ISSUANCE,
            OperationType.PROJECT_FUNDING: TransactionType.PROJECT_FUNDING_ISSUANCE,
            OperationType.PROJECT_REFUND: TransactionType.PROJECT_REFUND_ISSUANCE,
            OperationType.PROFIT_DISTRIBUTION: TransactionType.PROFIT_DISTRIBUTION_ISSUANCE,
            OperationType.LOSS_COVERAGE: TransactionType.LOSS_COVERAGE_ISSUANCE,
            OperationType.INTERNAL_TRANSFER: TransactionType.INTERNAL_TRANSFER_ISSUANCE,
            OperationType.LOAN: TransactionType.LOAN_ISSUANCE,
            OperationType.PURCHASE: TransactionType.PURCHASE_ISSUANCE,
            OperationType.SALE: TransactionType.SALE_ISSUANCE,
            OperationType.EXPENSE: TransactionType.EXPENSE_ISSUANCE,
            OperationType.CAPITAL_GAIN: TransactionType.CAPITAL_GAIN_ISSUANCE,
            OperationType.CAPITAL_LOSS: TransactionType.CAPITAL_LOSS_ISSUANCE,
        }
        return mapping.get(self.operation_type)

    @property
    def _payment_transaction_type(self):
        """Dynamic mapping for the payment leg"""
        mapping = {
            OperationType.CASH_INJECTION: TransactionType.CAPITAL_INJECTION_PAYMENT,
            OperationType.CASH_WITHDRAWAL: TransactionType.CAPITAL_WITHDRAWAL_PAYMENT,
            OperationType.PROJECT_FUNDING: TransactionType.PROJECT_FUNDING_PAYMENT,
            OperationType.PROJECT_REFUND: TransactionType.PROJECT_REFUND_PAYMENT,
            OperationType.PROFIT_DISTRIBUTION: TransactionType.PROFIT_DISTRIBUTION_PAYMENT,
            OperationType.LOSS_COVERAGE: TransactionType.LOSS_COVERAGE_PAYMENT,
            OperationType.INTERNAL_TRANSFER: TransactionType.INTERNAL_TRANSFER_PAYMENT,
            OperationType.LOAN: TransactionType.LOAN_PAYMENT,
            OperationType.PURCHASE: TransactionType.PURCHASE_PAYMENT,
            OperationType.SALE: TransactionType.SALE_COLLECTION,
            OperationType.EXPENSE: TransactionType.EXPENSE_PAYMENT,
            OperationType.CAPITAL_GAIN: TransactionType.CAPITAL_GAIN_PAYMENT,
            OperationType.CAPITAL_LOSS: TransactionType.CAPITAL_LOSS_PAYMENT,
            # OperationType.LOAN_REPAYMENT: TransactionType.LOAN_PAYMENT,
        }
        return mapping.get(self.operation_type)

    @property
    def _implicit_reversable_transaction_types(self):
        rv = []
        issuance = self._issuance_transaction_type
        if issuance:
            rv.append(issuance)
        if self._is_one_shot_operation:
            payment = self._payment_transaction_type
            if payment:
                rv.append(payment)
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
        return OperationType._is_one_shot_operation(self.operation_type)

    @property
    def has_repayments(self):
        return OperationType.has_repayments(self.operation_type)

    def get_cash_flow_balance(self):
        """
        Calculates the net cash balance of an operation.
        Logic: (Cash Out / Payment) - (Cash In / Repayment)
        """
        # 1. Get all valid (non-reversed) transactions
        valid_txs = self.get_all_transactions().filter(
            reversal_of__isnull=True,
            reversed_by__isnull=True,
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
        # TODO complete the logics
        if self.operation_type == OperationType.CASH_INJECTION:
            if not self.source.is_world:
                raise ValidationError("Injections source must be the World.")

    def clean_destination(self, **kwargs):
        # TODO: complete the logics
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
        return f"Operation {self.operation_type}: {self.amount} from {self.source} to {self.destination}"
