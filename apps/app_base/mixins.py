import typing
from decimal import Decimal
from typing import Union

from django.core.exceptions import ValidationError
from django.db import models
from django.db import transaction as db_transaction
from django.db.models import Q, Sum
from django.forms import ValidationError
from django.utils import timezone

if typing.TYPE_CHECKING:
    from apps.app_transaction.models import TransactionType

from .managers import SafeQuerySet

# TODO use database level constrains for dataintegrity.
# TODO add finiancial period closing

# -----------------------------
# Mixins
# -----------------------------


class BaseModelMixin:
    pk: models.BigAutoField
    all_objects: models.Manager

    def save(self, *args, **kwargs) -> None:
        return super().save(*args, **kwargs)  # type: ignore


class ImmutableMixin(BaseModelMixin):
    """Ensure the save() method will never update immutable fields"""

    _immutable_fields: dict[str, dict] = {}

    @property
    def immutable_field_names(self):
        rv = []
        for f in self._immutable_fields:
            rv.append(f if isinstance(f, str) else f[0])
        return rv

    def save(self, *args, **kwargs):
        if self.pk and self._immutable_fields:
            original = self.__class__.all_objects.only(*self.immutable_field_names).get(
                pk=self.pk
            )
            for field_name, field_kwargs in self._immutable_fields.items():
                allow_set = field_kwargs.get("ALLOW_SET", False)
                null_values = field_kwargs.get("NULL_VALUES", (None,))
                old_val = getattr(
                    original, field_name
                )  # don't add default, let the code to fail if the programmer pass incorrect var names
                new_val = getattr(self, field_name)
                if old_val == new_val:
                    continue
                if not allow_set or not (old_val in null_values):
                    raise ValidationError(f"You can't edit this field {field_name}")
        return super().save(*args, **kwargs)


class HasRelatedTransactions(BaseModelMixin):
    _related_transaction_name = "transactions"

    def get_all_transactions(self) -> SafeQuerySet:
        # Ensure your Transaction model has content_type and object_id fields
        from django.contrib.contenttypes.models import ContentType

        from apps.app_transaction.models import Transaction

        ct = ContentType.objects.get_for_model(self.__class__)
        # Return the QuerySet, don't just execute it!
        return Transaction.objects.filter(content_type=ct, object_id=self.pk)

    def get_undeleted_transactions(self):
        all = self.get_all_transactions()
        if all:
            return all.filter(deleted_at__isnull=True)
        return None


class AdjustableMixin(BaseModelMixin):
    """Easy wat to calculate the net amount after all adjustments"""

    _adjustments_related_name = "adjustments"

    @property
    def total_adjusted_amount(self):
        base = getattr(self, "amount", getattr(self, "total_amount", Decimal("0.00")))
        if not hasattr(self, self._adjustments_related_name):
            return base
        self.adjustments: models.QuerySet

        agg = self.adjustments.filter(
            deleted_at__isnull=True, reversed_by__isnull=True, reversal_of__isnull=True
        ).aggregate(
            inc=Sum("amount", filter=Q(effect="INCREASE")),
            dec=Sum("amount", filter=Q(effect="DECREASE")),
        )

        inc = agg["inc"] or Decimal("0.00")
        dec = agg["dec"] or Decimal("0.00")

        return base + inc - dec


class SourceFundMixin(BaseModelMixin):
    @property
    def payment_source_fund(self):
        raise NotImplementedError()

    def _validate_payment_source_fund_exists(self):
        if not self.payment_source_fund:
            raise ValidationError("Payment source fund is not existing.")

    def clean(self) -> None:
        self._validate_payment_source_fund_exists()
        return super().clean()


class TargetFundMixin(BaseModelMixin):
    @property
    def payment_target_fund(self):
        raise NotImplementedError()

    def _validate_payment_target_fund_exists(self):
        if not self.payment_target_fund:
            raise ValidationError("Payment target fund is not existing.")

    def clean(self) -> None:
        self._validate_payment_target_fund_exists()
        return super().clean()


# DEPERCATED
# USE more clear mixin
# There is 2 cases:
# The payer pay the amount in multiple transactions
# The payer recieve a repayment ( like debt repayment )
# This class was handling both which is incorrect.
# So write another 2 classes
class SettlableMixin(HasRelatedTransactions, BaseModelMixin):
    # N.B:. This mixin requires definition of the following properties
    # in the child models:
    # - recever_fund
    # - _related_transaction_name
    # - total_adjusted_amount (provided by inherit from the adjustableMixin)

    settlement_type: Union["TransactionType", None] = None
    _amount_field_name = "amount"

    @property
    def payment_target_fund(self):
        raise NotImplementedError()

    @property
    def amount_settled(self):
        """
        Standardizes cash movement regardless of document type.
        """
        # valid transactions returns all transactions
        # except: the reversed, the reversals & the deleted ones.
        # So, the reversed transactions are exclused from the start.
        # No need for another guard.
        valid_txs = self.get_undeleted_transactions()
        if not valid_txs:
            return Decimal("0")
        # Filter the valid transaction & get the payment only transactions
        valid_txs = valid_txs.filter(type=self.settlement_type)
        # We define 'settlement' as money moving toward the Receiver
        # from the Payer as defined in the document.
        to_receiver = valid_txs.filter(target=self.payment_target_fund).aggregate(
            total=Sum(self._amount_field_name)
        )["total"] or Decimal("0.00")

        # We define 'refund' as money moving back to the Payer
        from_receiver = valid_txs.filter(source=self.payment_target_fund).aggregate(
            total=Sum(self._amount_field_name)
        )["total"] or Decimal("0.00")

        return to_receiver - from_receiver

    @property
    def total_adjusted_amount(self):
        try:
            return super().total_adjusted_amount
        except:
            return self.amount

    @property
    def amount_remaining_to_settle(self):
        # Using max(0, ...) prevents 'negative' remaining amounts if someone overpays
        # return max(Decimal("0.00"), self.total_adjusted_amount - self.amount_settled)
        return self.total_adjusted_amount - self.amount_settled

    @property
    def is_fully_settled(self):
        # Precision check: useful when dealing with floating point math / Decimals
        return self.amount_settled >= self.total_adjusted_amount

    def validate_settlement_amount(self, amount_to_pay: Decimal):
        # Todo use calculate repayments in the methods
        if amount_to_pay <= 0:
            raise ValidationError("The amount should be more than 0")
        if amount_to_pay > self.amount_remaining_to_settle:
            # We allow a small margin for rounding or explicitly block overpayment
            raise ValidationError(
                f"The payed amount {amount_to_pay} exceeds the remaining: {self.amount_remaining_to_settle}"
            )
        return True


class AmountCleanMixin(BaseModelMixin):
    """Ensure amount will never be zero or less"""

    _amount_name = "amount"

    def clean(self) -> None:
        amount = getattr(
            self, self._amount_name
        )  # don't add default, let the code to fail if the var name is incorrect
        if amount <= 0:
            raise ValidationError(f"Amount should be positive, got {amount}")
        return super().clean()


class LinkedIssuanceTransactionMixin(SourceFundMixin, TargetFundMixin, BaseModelMixin):
    _issuance_transaction_type: "TransactionType"

    @property
    def _has_issuance_transaction(self):
        """Indicates if this reord can/should be linked to a transaction that its type is *_Issuance"""
        return getattr(self, "_issuance_transaction_type", None) is not None

    def create_issuance_transaction(
        self, description="", note="", officer=None, date=None
    ):
        from apps.app_transaction.models import Transaction

        with db_transaction.atomic():
            return Transaction.create(
                source=self.payment_source_fund,
                target=self.payment_target_fund,
                document=self,
                type=self._issuance_transaction_type,
                amount=self.amount,
                officer=officer or self.officer,
                description=description
                or f"Issuance transaction for ({self.__class__}) ({self.pk})",
                note=note,
                date=date or timezone.now(),
            )

    def save(self, *args, **kwargs) -> None:
        with db_transaction.atomic():
            is_new = self.pk is None
            create_transactions = kwargs.pop("create_transactions", True)
            # rv = super().save(*args, **kwargs)

            if is_new and create_transactions:
                if getattr(self, "reversal_of", None) is not None and self.reversal_of:
                    # Don't create transactions
                    ...
                if getattr(self, "reversed_by", None) is not None and self.reversed_by:
                    # Don't create transactions
                    ...
                else:
                    if self._has_issuance_transaction:
                        kwargs.setdefault("tasks", []).append(
                            (self.create_issuance_transaction, (), {})
                        )
                        # self.create_issuance_transaction()
            return super().save(*args, **kwargs)


class LinkedPaymentTransactionMixin(SourceFundMixin, TargetFundMixin, BaseModelMixin):
    # Flags:
    max_payment_transaction_count = 0
    # Indicates that this record
    # _has_issuance_transaction = True
    # _has_single_payment_transactions = True
    # _has_multiple_payment_transactions = False
    # and once created, it should creates
    # the issuance transaction
    # and the single payment transaction
    _is_one_shot_operation = False
    # End of flags
    # ################################################
    # Indicates the type of the issuance transaction
    _issuance_transaction_type: "TransactionType"
    _payment_transaction_type: "TransactionType"

    @property
    def _has_payment_transaction(self):
        """indicates whther this record can be linked to one or more transactions"""
        return getattr(self, "_payment_transaction_type", None) is not None

    @property
    def _has_single_payment_transaction(self):
        """Indicates if this record can/should be linked to a single transaction of type payment"""
        return self._has_payment_transaction and self.max_payment_transaction_count == 1

    @property
    def _has_multiple_payment_transactions(self):
        """Indicates if this record can/should be linked to more than one payment transaction"""
        return (
            self._has_payment_transaction and self.max_payment_transaction_count == -1
        )

    def create_payment_transaction(
        self, amount, officer, date, description="", note=""
    ):
        from apps.app_transaction.models import Transaction

        with db_transaction.atomic():
            return Transaction.create(
                source=self.payment_source_fund,
                target=self.payment_target_fund,
                document=self,
                type=self._payment_transaction_type,
                amount=amount,
                officer=officer or self.officer,
                description=description
                or f"Payment transaction for ({self.__class__}) ({self.pk})",
                note=note,
                date=date or timezone.now(),
            )

    def save(self, *args, **kwargs) -> None:
        with db_transaction.atomic():
            is_new = self.pk is None
            create_transactions = kwargs.pop("create_transactions", True)
            # rv = super().save(*args, **kwargs)
            if is_new and create_transactions:
                if getattr(self, "reversal_of", None) is not None and self.reversal_of:
                    # Don't create transactions
                    ...
                if getattr(self, "reversed_by", None) is not None and self.reversed_by:
                    # Don't create transactions
                    ...
                else:
                    if self._is_one_shot_operation:
                        if not self._has_single_payment_transaction:
                            raise ValidationError(
                                "This record can't act as shot operation record"
                            )
                        kwargs.setdefault("tasks", []).append(
                            (
                                self.create_payment_transaction,
                                (),
                                {
                                    "amount": self.amount,
                                    "officer": self.officer,
                                    "date": self.date or timezone.now(),
                                    "description": f"One shot payment transactiof for ({self.__class__}) ({self.pk})",
                                },
                            )
                        )
                        # self.create_payment_transaction(
                        #     amount=self.amount,
                        #     officer=self.officer,
                        #     date=self.date or timezone.now(),
                        #     description=f"One shot payment transactiof for ({self.__class__}) ({self.pk})",
                        # )
            return super().save(*args, **kwargs)


class OfficerMixin(BaseModelMixin):
    officer = models.ForeignKey(
        "app_entity.Entity",
        on_delete=models.PROTECT,
        null=False,
        blank=False,
        limit_choices_to={"is_staff": True},
    )

    def clean(self):
        from apps.app_entity.models import ENTITY_TYPE_ENUM

        if not self.officer.type == ENTITY_TYPE_ENUM.PERSONAL:
            raise ValidationError(
                f"Officier should be of type `PERSONAL` entity. not {self.officer.type}"
            )
        if not self.officer.user:
            raise ValidationError("Officer should have assciated user account.")
        if not self.officer.user.is_staff:
            raise ValidationError("Officer should be staff person.")
        if not self.officer.active:
            raise ValidationError("Officer should be `active`")
        return super().clean()
