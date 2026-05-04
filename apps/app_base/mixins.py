import typing
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db import transaction as db_transaction
from django.db.models import Q, Sum
from django.forms import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

if typing.TYPE_CHECKING:
    from apps.app_transaction.transaction_type import TransactionType

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
                    raise ValidationError(
                        _("You can't edit this field %(field_name)s")
                        % {"field_name": field_name}
                    )
        return super().save(*args, **kwargs)


class AmountCleanMixin(BaseModelMixin):
    """Ensure amount will never be zero or less"""

    _amount_name = "amount"

    def clean(self) -> None:
        amount = getattr(
            self, self._amount_name
        )  # don't add default, let the code to fail if the var name is incorrect
        if amount <= 0:
            raise ValidationError(
                _("Amount should be positive, got %(amount)s") % {"amount": amount}
            )
        return super().clean()


class OfficerMixin(BaseModelMixin):
    def clean(self):
        if not self.officer.is_staff:
            raise ValidationError(_("Officer should be a staff user."))
        if not self.officer.is_active:
            raise ValidationError(_("Officer should be an active user."))
        return super().clean()


class AdjustableMixin(BaseModelMixin):
    """Easy wat to calculate the net amount after all adjustments"""

    _adjustments_related_name = "adjustments"
    _amount_field_name = "amount"

    @property
    def effective_amount(self):
        if not hasattr(self, self._amount_field_name):
            raise AttributeError(
                _("%(class)s must define amount field %(field)s.")
                % {"class": self.__class__.__name__, "field": self._amount_field_name}
            )
        base_val = getattr(self, self._amount_field_name, Decimal("0.00"))
        adjustments_mgr = getattr(self, self._adjustments_related_name, None)
        if not adjustments_mgr:
            return Decimal(base_val)

        from apps.app_adjustment.models import AdjustmentType

        reduction_types = [t for t in AdjustmentType if AdjustmentType.is_reduction(t)]

        active_qs = adjustments_mgr.filter(
            reversed_by__isnull=True,
            reversal_of__isnull=True,
            deleted_at__isnull=True,
        )
        stats = active_qs.aggregate(
            inc=Sum("amount", filter=~Q(type__in=reduction_types)),
            dec=Sum("amount", filter=Q(type__in=reduction_types)),
        )

        inc = stats["inc"] or Decimal("0.00")
        dec = stats["dec"] or Decimal("0.00")

        return base_val + inc - dec


class SourceFundMixin(BaseModelMixin):
    @property
    def payment_source_fund(self):
        raise NotImplementedError()

    def _validate_payment_source_fund_exists(self):
        try:
            if not self.payment_source_fund:
                raise ValidationError(_("Payment source fund is not existing."))
        except Exception:
            raise ValidationError(_("Payment source fund could not be resolved."))
        fund = self.payment_source_fund
        if not fund.active:
            raise ValidationError(_("The Payment source entity should be active."))
        if not fund.active:
            raise ValidationError(_("The payment source fund is not active."))

    def clean(self) -> None:
        self._validate_payment_source_fund_exists()
        return super().clean()


class TargetFundMixin(BaseModelMixin):
    @property
    def payment_target_fund(self):
        raise NotImplementedError()

    def _validate_payment_target_fund_exists(self):
        try:
            if not self.payment_target_fund:
                raise ValidationError(_("Payment target fund is not existing."))
        except Exception:
            raise ValidationError(_("Payment target fund could not be resolved."))
        fund = self.payment_target_fund
        if not fund.active:
            raise ValidationError(_("The Payment target entity should be active."))

    def clean(self) -> None:
        self._validate_payment_target_fund_exists()
        return super().clean()


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
        return self.get_all_transactions().filter(deleted_at__isnull=True)


class LinkedIssuanceTransactionMixin(
    SourceFundMixin, TargetFundMixin, HasRelatedTransactions, BaseModelMixin
):
    _issuance_transaction_type: "TransactionType"

    @property
    def _has_issuance_transaction(self) -> bool:
        """Indicates if this reord can/should be linked to a transaction that its type is *_Issuance"""
        return getattr(self, "_issuance_transaction_type", None) is not None

    def create_issuance_transaction(
        self, description="", note="", officer=None, date=None
    ):
        existing = self.get_all_transactions().filter(
            type=self._issuance_transaction_type,
            reversal_of__isnull=True,
        )
        if existing.exists():
            raise ValidationError(
                _("An issuance transaction already exists for this operation.")
            )
        from apps.app_transaction.models import Transaction

        with db_transaction.atomic():
            return Transaction.create(
                source=self.payment_source_fund,
                target=self.payment_target_fund,
                document=self,
                tx_type=self._issuance_transaction_type,
                amount=self.amount,
                officer=officer or self.officer,
                description=description
                or _("Issuance transaction for (%(class)s) (%(pk)s)")
                % {"class": self.__class__.__name__, "pk": self.pk},
                note=note,
                date=date or timezone.now(),
            )

    def save(self, *args, **kwargs) -> None:
        with db_transaction.atomic():
            is_new = self.pk is None
            if is_new:
                if getattr(self, "reversal_of", None) is not None and self.reversal_of:
                    # Don't create transactions
                    ...
                elif (
                    getattr(self, "reversed_by", None) is not None and self.reversed_by
                ):
                    # Don't create transactions
                    ...
                else:
                    if self._has_issuance_transaction:
                        kwargs.setdefault("post_save_tasks", []).append(
                            (self.create_issuance_transaction, (), {"date": self.date})
                        )
            return super().save(*args, **kwargs)


class LinkedPaymentTransactionMixin(
    SourceFundMixin, TargetFundMixin, HasRelatedTransactions, BaseModelMixin
):
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
    # Whether to enforce a fund balance check before creating a payment transaction.
    # Set to True on operations where the payer is a real person/project entity.
    # For one-shot operations this check runs at creation time (failing the whole op);
    # for partial-payment operations it runs per payment while issuance is unrestricted.
    # Leave False for operations whose payer is the system/world entity, or for
    # admin correction operations that must never be blocked by fund balance.
    check_balance_on_payment = False
    # End of flags
    # ################################################
    # Indicates the type of the issuance transaction
    _payment_transaction_type: "TransactionType"
    _amount_field_name = "amount"

    @property
    def amount_settled(self):
        # valid transactions returns all transactions
        # except: the reversed, the reversals & the deleted ones.
        # So, the reversed transactions are exclused from the start.
        # No need for another guard.
        valid_txs = self.get_undeleted_transactions()
        if not valid_txs:
            return Decimal("0")
        # Filter the valid transaction & get the payment only transactions
        valid_txs = valid_txs.filter(type=self._payment_transaction_type)
        # We define 'settlement' as money moving toward the Receiver
        # from the Payer as defined in the document.
        to_receiver = valid_txs.filter(target=self.payment_target_fund).aggregate(
            total=Sum(self._amount_field_name)
        )["total"] or Decimal("0.00")
        # TODO: Why I write something like this ?
        # I don't know
        # So comment now.
        # We define 'refund' as money moving back to the Payer
        from_receiver = valid_txs.filter(source=self.payment_target_fund).aggregate(
            total=Sum(self._amount_field_name)
        )["total"] or Decimal("0.00")

        return to_receiver - from_receiver

    @property
    def total_settlable_amount(self):
        if hasattr(self, "effective_amount"):
            return self.effective_amount
        return getattr(self, self._amount_field_name, 0)

    @property
    def amount_remaining_to_settle(self):
        # Using max(0, ...) prevents 'negative' remaining amounts if someone overpays
        # return max(Decimal("0.00"), self.total_settlable_amount - self.amount_settled)
        return self.total_settlable_amount - self.amount_settled

    @property
    def is_fully_settled(self) -> bool:
        # Precision check: useful when dealing with floating point math / Decimals
        return self.amount_settled >= self.total_settlable_amount

    @property
    def is_overpayed_settled(self) -> bool:
        # Precision check: useful when dealing with floating point math / Decimals
        return self.amount_settled > self.total_settlable_amount

    def validate_settlement_amount(self, amount_to_pay: Decimal):
        # Todo use calculate repayments in the methods
        if amount_to_pay <= 0:
            raise ValidationError(_("The amount should be more than 0"))
        if amount_to_pay > self.amount_remaining_to_settle:
            # We allow a small margin for rounding or explicitly block overpayment
            raise ValidationError(
                _("The paid amount %(amount)s exceeds the remaining: %(remaining)s")
                % {
                    "amount": amount_to_pay,
                    "remaining": self.amount_remaining_to_settle,
                }
            )
        return True

    @property
    def _has_payment_transaction(self) -> bool:
        """indicates whther this record can be linked to one or more transactions"""
        return getattr(self, "_payment_transaction_type", None) is not None

    @property
    def _has_single_payment_transaction(self) -> bool:
        """Indicates if this record can/should be linked to a single transaction of type payment"""
        return self._has_payment_transaction and self.max_payment_transaction_count == 1

    @property
    def _has_multiple_payment_transactions(self) -> bool:
        """Indicates if this record can/should be linked to more than one payment transaction"""
        return (
            self._has_payment_transaction and self.max_payment_transaction_count == -1
        )

    def create_payment_transaction(
        self, amount, officer, date, description="", note=""
    ):
        from apps.app_transaction.models import Transaction

        if self.check_balance_on_payment:
            fund = self.payment_source_fund
            if not fund.can_pay(amount):
                raise ValidationError(
                    _(
                        "Insufficient funds: fund balance (%(balance)s) is less than the payment amount (%(amount)s)."
                    )
                    % {"balance": fund.balance, "amount": amount}
                )

        if self._is_one_shot_operation:
            existing = self.get_all_transactions().filter(
                type=self._payment_transaction_type
            )
            if existing.exists():
                raise ValidationError(
                    _("One-shot operations can only have a single payment transaction.")
                )
            if amount != self.amount:
                raise ValidationError(
                    _(
                        "Payment amount %(amount)s must match the operation amount %(op_amount)s."
                    )
                    % {"amount": amount, "op_amount": self.amount}
                )

        self.validate_settlement_amount(amount)
        with db_transaction.atomic():
            return Transaction.create(
                source=self.payment_source_fund,
                target=self.payment_target_fund,
                document=self,
                tx_type=self._payment_transaction_type,
                amount=amount,
                officer=officer or self.officer,
                description=description
                or _("Payment transaction for (%(class)s) (%(pk)s)")
                % {"class": self.__class__.__name__, "pk": self.pk},
                note=note,
                date=date or timezone.now(),
            )

    def save(self, *args, **kwargs) -> None:
        with db_transaction.atomic():
            is_new = self.pk is None
            if is_new:

                if getattr(self, "reversal_of", None) is not None and self.reversal_of:
                    # Don't create transactions
                    ...
                elif (
                    getattr(self, "reversed_by", None) is not None and self.reversed_by
                ):
                    # Don't create transactions
                    ...
                else:
                    if self._is_one_shot_operation:
                        if not self._has_single_payment_transaction:
                            raise ValidationError(
                                _(
                                    "This record can't act as a one-shot operation record"
                                )
                            )
                        kwargs.setdefault("post_save_tasks", []).append(
                            (
                                self.create_payment_transaction,
                                (),
                                {
                                    "amount": self.amount,
                                    "officer": self.officer,
                                    "date": self.date or timezone.now(),
                                    "description": _(
                                        "One shot payment transaction for (%(class)s) (%(pk)s)"
                                    )
                                    % {"class": self.__class__.__name__, "pk": self.pk},
                                },
                            )
                        )
            return super().save(*args, **kwargs)


class LinkedRePaymentTransactionMixin(
    SourceFundMixin, TargetFundMixin, HasRelatedTransactions, BaseModelMixin
):
    # ################################################
    # Indicates the type of the issuance transaction
    _repayment_transaction_type: "TransactionType"
    _amount_field_name = "amount"
    _tx_amount_field_name = "amount"
    is_repayable = False

    @property
    def total_repayable_amount(self):
        if hasattr(self, "effective_amount"):
            return self.effective_amount
        return getattr(self, self._amount_field_name, Decimal("0.00"))

    @property
    def amount_repayed(self):
        valid_txs = self.get_undeleted_transactions()
        if not valid_txs:
            return Decimal("0")
        if hasattr(self, "_repayment_transaction_type"):
            valid_txs = valid_txs.filter(type=self._repayment_transaction_type)
        to_source = valid_txs.filter(target=self.payment_source_fund).aggregate(
            total=Sum(self._tx_amount_field_name)
        )["total"] or Decimal("0.00")
        return to_source

    @property
    def amount_remaining_to_repay(self):
        return self.total_repayable_amount - self.amount_repayed

    @property
    def is_fully_repayed(self) -> bool:
        return self.amount_repayed >= self.total_repayable_amount

    @property
    def is_overpaid_repayed(self) -> bool:
        return self.amount_repayed > self.total_repayable_amount

    def validate_repayement_amount(self, amount_to_pay: Decimal):
        if amount_to_pay <= 0:
            raise ValidationError(_("The amount should be more than 0"))
        if amount_to_pay > self.amount_remaining_to_repay:
            # We allow a small margin for rounding or explicitly block overpayment
            raise ValidationError(
                _("The paid amount %(amount)s exceeds the remaining: %(remaining)s")
                % {"amount": amount_to_pay, "remaining": self.amount_remaining_to_repay}
            )
        return True

    @property
    def _has_repayment_transaction(self) -> bool:
        """indicates whther this record can be linked to one or more transactions"""
        return getattr(self, "_repayment_transaction_type", None) is not None

    def create_repayment_transaction(
        self, amount, officer, date, description="", note=""
    ):
        from apps.app_transaction.models import Transaction

        self.validate_repayement_amount(amount)

        with db_transaction.atomic():
            return Transaction.create(
                source=self.payment_target_fund,
                target=self.payment_source_fund,
                document=self,
                tx_type=self._repayment_transaction_type,
                amount=amount,
                officer=officer or self.officer,
                description=description
                or _("RePayment transaction for (%(class)s) (%(pk)s)")
                % {"class": self.__class__.__name__, "pk": self.pk},
                note=note,
                date=date or timezone.now(),
            )
