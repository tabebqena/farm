import typing
from decimal import Decimal
from typing import Tuple, Union

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum
from django.forms import ValidationError

if typing.TYPE_CHECKING:
    from app_accounting.models.transaction import TransactionType

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

    def get_all_transactions(self) -> Union[None, SafeQuerySet]:
        tx_queryset = getattr(self, self._related_transaction_name, None)
        if tx_queryset is None:
            return None
        # Optimizing with select_related for the funds usually helps performance here
        return tx_queryset

    def get_undeleted_transactions(self):
        all = self.get_all_transactions()
        if all:
            return all.filter(deleted_at__isnull=True)
        return None

    def get_valid_transactions(self) -> Union[None, SafeQuerySet]:
        tx_queryset = getattr(self, self._related_transaction_name, None)
        if tx_queryset is None:
            return None

        # Optimizing with select_related for the funds usually helps performance here
        return tx_queryset.filter(
            deleted_at__isnull=True,
            reversed_by__isnull=True,
            reversal_of__isnull=True,  # Important: Exclude the counter-records too
        )


class AdjustableMixin(BaseModelMixin):
    @property
    def total_adjusted_amount(self):
        base = getattr(self, "amount", getattr(self, "total_amount", Decimal("0.00")))
        if not hasattr(self, "adjustments"):
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


class SettlableMixin(HasRelatedTransactions, BaseModelMixin):
    # N.B:. This mixin requires definition of the following properties
    # in the child models:
    # - recever_fund
    # - _related_transaction_name
    # - total_adjusted_amount (provided by inherit from the adjustableMixin)
    # - get_valid_transactions method (inherited from the HASRElatedTransaction)

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
        valid_txs = self.get_valid_transactions()
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
    _amount_name = "amount"

    def clean(self) -> None:
        amount = getattr(
            self, self._amount_name
        )  # don't add default, let the code to fail if the var name is incorrect
        if amount <= 0:
            raise ValidationError(f"Amount should be positive, got {amount}")
        return super().clean()


class MayHasFundMixin(BaseModelMixin):
    @property
    def has_fund(self):
        return getattr(self, "fund", None) is not None
