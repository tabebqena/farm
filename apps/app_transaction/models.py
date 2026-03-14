import typing
from decimal import Decimal

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.db import transaction as db_transaction
from django.forms import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.app_base.mixins import AmountCleanMixin, ImmutableMixin
from apps.app_base.models import BaseModel

if typing.TYPE_CHECKING:
    from apps.app_entity.models import Entity, Fund
# TODO use database level constrains for dataintegrity.
# TODO add finiancial period closing
# TODO : "Financial Statement" method
# TODO: Integrity check method


# -----------------------------
# Transaction
# -----------------------------
class TransactionType(models.TextChoices):
    # --- Operational ---
    REVENUE = ("REVENUE", "REVENUE")
    OTHER_INCOME = ("OTHER_INCOME", "OTHER_INCOME")
    TAX_PAYMENT = ("TAX_PAYMENT", "TAX_PAYMENT")
    INVOICE_ADJUSTMENT = ("INVOICE_ADJUSTMENT", "INVOICE_ADJUSTMENT")
    EXPENSE_ADJUSTMENT = ("EXPENSE_ADJUSTMENT", "EXPENSE_ADJUSTMENT")
    PAYROLL_ADJUSTMENT = ("PAYROLL_ADJUSTMENT", "PAYROLL_ADJUSTMENT")

    PURCHASE_ISSUANCE = ("PURCHASE_ISSUANCE", "PURCHASE_ISSUANCE")
    PURCHASE_PAYMENT = ("PURCHASE_PAYMENT", "PURCHASE_PAYMENT")
    PURCHASE_RETURN = ("PURCHASE_RETURN", "PURCHASE_RETURN")
    SALE_ISSUANCE = ("SALE_ISSUANCE", "SALE_ISSUANCE")
    EXPENSE_ISSUANCE = ("EXPENSE_ISSUANCE", "EXPENSE_ISSUANCE")
    EXPENSE_PAYMENT = ("EXPENSE_PAYMENT", "EXPENSE_PAYMENT")

    # --- Workers (Strict 1:1 Pairs) ---
    WORKER_WAGE = ("WORKER_WAGE", "WORKER_WAGE")
    # SALARY_INCOME = (
    #     "SALARY_INCOME",
    #     "SALARY_INCOME",
    # )  # Mirror of WORKER_WAGE

    WORKER_ADVANCE = ("WORKER_ADVANCE", "WORKER_ADVANCE")  # سلفة
    # ADVANCE_RECEIPT = (
    #     "ADVANCE_RECEIPT",
    #     "WORKER_ADVANCE",
    # )  # Mirror of WORKER_ADVANCE
    ADVANCE_REPAYMENT = ("ADVANCE_REPAYMENT", "ADVANCE_REPAYMENT")  # سداد سلفة
    # ADVANCE_COLLECTION = (
    #     "ADVANCE_COLLECTION",
    #     "ADVANCE_COLLECTION",
    # )  # Mirror of ADVANCE_REPAYMENT

    # --- Capital & Partners ---
    CAPITAL_INJECTION_ISSUANCE = (
        "CAPITAL_INJECTION_ISSUANCE",
        "CAPITAL_INJECTION_ISSUANCE",
    )

    CAPITAL_INJECTION_PAYMENT = (
        "CAPITAL_INJECTION_PAYMENT",
        "CAPITAL_INJECTION_PAYMENT",
    )

    CAPITAL_WITHDRAWAL_ISSUANCE = (
        "CAPITAL_WITHDRAWAL_ISSUANCE",
        "CAPITAL_WITHDRAWAL_ISSUANCE",
    )

    CAPITAL_WITHDRAWAL_PAYMENT = (
        "CAPITAL_WITHDRAWAL_PAYMENT",
        "CAPITAL_WITHDRAWAL_PAYMENT",
    )

    CAPITAL_GAIN_ISSUANCE = (
        "CAPITAL_GAIN_ISSUANCE",
        "CAPITAL_GAIN_ISSUANCE",
    )
    CAPITAL_LOSS_ISSUANCE = (
        "CAPITAL_LOSS_ISSUANCE",
        "CAPITAL_LOSS_ISSUANCE",
    )

    LOSS_COVERAGE_ISSUANCE = (
        "LOSS_COVERAGE_ISSUANCE",
        "LOSS_COVERAGE_ISSUANCE",
    )

    LOSS_COVERAGE_PAYMENT = (
        "LOSS_COVERAGE_PAYMENT",
        "LOSS_COVERAGE_PAYMENT",
    )

    PROFIT_DISTRIBUTION_ISSUANCE = (
        "PROFIT_DISTRIBUTION_ISSUANCE",
        "PROFIT_DISTRIBUTION_ISSUANCE",
    )
    PROFIT_DISTRIBUTION_PAYMENT = (
        "PROFIT_DISTRIBUTION_PAYMENT",
        "PROFIT_DISTRIBUTION_PAYMENT",
    )

    # PROFIT_COLLECTION = ("PROFIT_COLLECTION", "PROFIT_COLLECTION")

    # --- Projects ---
    PROJECT_FUNDING_ISSUANCE = (
        "PROJECT_FUNDING_ISSUANCE",
        "PROJECT_FUNDING_ISSUANCE",
    )

    PROJECT_FUNDING_PAYMENT = (
        "PROJECT_FUNDING_PAYMENT",
        "PROJECT_FUNDING_PAYMENT",
    )
    PROJECT_REFUND_ISSUANC = (
        "PROJECT_REFUND_ISSUANC",
        "PROJECT_REFUND_ISSUANC",
    )
    PROJECT_REFUND_PAYMENT = (
        "PROJECT_REFUND_PAYMENT",
        "PROJECT_REFUND_PAYMENT",
    )

    # --- Loans & Debts (Strict 1:1 Pairs) ---
    # LOAN_ISSUANCE = ("LOAN_ISSUANCE", "LOAN_ISSUANCE")  # إصدار قرض للغير
    # LOAN_RECEIVED_BY_OTHER = (
    #     "LOAN_RECEIVED_BY_OTHER",
    #     "LOAN_RECEIVED_BY_OTHER",
    # )  # استلام قرض (عند الطرف الآخر)

    # LOAN_REPAYMENT_BY_OTHER = (
    #     "LOAN_REPAYMENT_BY_OTHER",
    #     "LOAN_REPAYMENT_BY_OTHER",
    # )  # سداد قرض (من الغير)
    # LOAN_RECOVERY = ("LOAN_RECOVERY", "LOAN_RECOVERY")  # استرداد قرض (عندنا)
    LOAN_ISSUANCE = (
        "LOAN_ISSUANCE",
        "LOAN_ISSUANCE",
    )
    LOAN_PAYMENT = (
        "LOAN_PAYMENT",
        "LOAN_PAYMENT",
    )
    LOAN_REPAYMENT = ("LOAN_REPAYMENT", "LOAN_REPAYMENT")
    # DEBT_RECEIVED = ("DEBT_RECEIVED", "DEBT_RECEIVED")  # استلام دين (قرض لنا)
    # DEBT_GIVEN_BY_LENDER = (
    #     "DEBT_GIVEN_BY_LENDER",
    #     "DEBT_GIVEN_BY_LENDER",
    # )  # تقديم دين (عند المقرض)

    # DEBT_SETTLEMENT_BY_LENDER = (
    #     "DEBT_SETTLEMENT_BY_LENDER",
    #     "DEBT_SETTLEMENT_BY_LENDER",
    # )

    # --- Internal ---
    INTERNAL_TRANSFER_ISSUANCE = (
        "INTERNAL_TRANSFER_ISSUANCE",
        "INTERNAL_TRANSFER_ISSUANCE",
    )
    INTERNAL_TRANSFER_PAYMENT = (
        "INTERNAL_TRANSFER_PAYMENT",
        "INTERNAL_TRANSFER_PAYMENT",
    )


class Transaction(AmountCleanMixin, ImmutableMixin, BaseModel):
    _immutable_fields = (
        "source",
        "target",
        "type",
        "amount",
        "officer",
        ("reversal_of", {"ALLOW_SET": True}),  # type: ignore
    )  # type: ignore
    date = models.DateTimeField(default=timezone.now)
    # source is the fund that gives the amount.
    source = models.ForeignKey(
        "app_entity.Fund",
        on_delete=models.PROTECT,
        related_name="transactions_outgoing",
        blank=False,
        null=False,
    )
    # target is the fund that receives the amount.
    target = models.ForeignKey(
        "app_entity.Fund",
        on_delete=models.PROTECT,
        related_name="transactions_incoming",
        blank=False,
        null=False,
    )
    type = models.CharField(
        max_length=50, null=False, blank=False, choices=TransactionType.choices
    )
    amount = models.DecimalField(max_digits=20, decimal_places=2)

    description = models.TextField(blank=False, null=False)
    note = models.TextField(blank=True)
    reversal_of = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reversed_by",
    )

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        related_name="transactions",
    )
    object_id = models.PositiveIntegerField(null=False, blank=False)
    document = GenericForeignKey("content_type", "object_id")

    officer = models.ForeignKey(
        "app_entity.Entity",
        on_delete=models.PROTECT,
        related_name="transactions_supervised",
    )

    @property
    def owner(self):
        return self.document

    @property
    def is_reversed(self):
        return getattr(self, "reversed_by", None) is not None

    @property
    def is_reversal(self):
        return self.reversal_of is not None

    # Map Document Models to their permitted TransactionTypes
    DOCUMENT_TYPE_MAP = {
        "operation": {
            "CASH_INJECTION": [
                TransactionType.CAPITAL_INJECTION_ISSUANCE,
                TransactionType.CAPITAL_INJECTION_PAYMENT,
            ]
        },
    }

    def clean_type(self, **kwargs):
        document = self.document
        model_name = self.content_type.model
        return

        # Validation for your new centralized 'FinancialOperation' model
        if model_name == "operation":
            op_type = getattr(document, "operation_type", None)

            # 1. Verify the Transaction Type matches the Operation Type
            allowed_types = Transaction.DOCUMENT_TYPE_MAP.get(model_name, {}).get(
                op_type, []
            )
            if self.type not in allowed_types:
                raise ValidationError(
                    f"Invalid Transaction Type: '{self.type}' is not allowed "
                    f"for a financial operation of type '{op_type}'."
                    f"allowed types: {allowed_types}"
                )

            # 2. Verify Fund Directionality
            # For Injections: Target MUST be an Internal Person's fund
            if op_type == "CASH_INJECTION" and not self.is_reversal:
                if not self.target.entity.is_internal or not self.target.entity.person:
                    raise ValidationError(
                        "Cash Injections must target an Internal Person's fund."
                    )
                if not self.source.entity.is_world:
                    raise ValidationError(
                        "Cash Injections must sourced from the world fund."
                    )

            # For Project Funding: Target MUST be a Project fund
            if op_type == "PROJECT_FUNDING":
                if not self.target.entity.is_project:
                    raise ValidationError(
                        "Project Funding must target a Project's fund."
                    )

        # # 3. Generic Document Safety
        # if self.amount != document.amount and not self.reversal_of:
        #     # Note: Only check this for 'Issuance' types,
        #     # as 'Payment' types might be partial.
        #     if "_ISSUANCE" in self.type.name:
        #         raise ValidationError(
        #             "Transaction amount must match the source document amount."
        #         )

    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)

    def clean(self) -> None:
        if self.source == self.target:
            raise ValidationError("Source and target funds must be different.")
        if self.content_type:
            model_name = self.content_type.model  # lowercase model name

            # 1. Ensure the model is even allowed to create transactions
            if model_name not in Transaction.DOCUMENT_TYPE_MAP:
                raise ValidationError(
                    f"Entities of type '{model_name}' are not authorized to issue ledger transactions."
                )
        return super().clean()

    @staticmethod
    def create(
        source: "Fund",
        target: "Fund",
        document,
        type: TransactionType,
        amount: Decimal,
        officer: "Entity",
        description="",
        note="",
        date=None,
    ):
        return Transaction.objects.create(
            source=source,
            target=target,
            type=type,
            document=document,
            amount=amount,
            officer=officer or document.officer,
            description=description or f"Transaction for {document.description}",
            note=note,
            date=date or timezone.now(),
        )

    @db_transaction.atomic
    def reverse(self, officer, reason="", date=None):
        """
        Creates a counter-transaction to neutralize this transaction.
        """
        if self.reversal_of:
            raise ValidationError(
                "Cannot reverse a transaction that is already a reversal."
            )
        if hasattr(self, "reversed_by") and self.reversed_by:  # type: ignore
            raise ValidationError("This transaction has already been reversed.")
        # Use the same type in the reversal to make it readable
        # This has no effect in calculations
        # 1. Create the mirror-image Transaction
        reversal = Transaction(
            date=date or timezone.now(),
            source=self.target,
            target=self.source,
            amount=self.amount,
            type=self.type,
            officer=officer,
            reversal_of=self,  #
            description=f"REVERSAL of ID {self.id}: {reason}",
            content_type=self.content_type,
            object_id=self.object_id,
            document=self.document,
        )
        reversal.save()
        setattr(self, "reversed_by", reversal)
        # self.refresh_from_db()
        return reversal

    def get_absolute_url(self):
        return reverse("transaction_detail", kwargs={"transaction_pk": self.pk})
