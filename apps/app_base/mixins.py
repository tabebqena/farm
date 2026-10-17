"""Reusable model mixins shared across the project.

Provides common behaviour used by many models: protecting immutable fields
(:class:`ImmutableMixin`), cleaning monetary amounts (:class:`AmountCleanMixin`),
recording an officer (:class:`OfficerMixin`), computing adjustable effective
amounts (:class:`AdjustableMixin`), linking payment source / target funds, and
automatically creating the related transactions for issuances, payments and
repayments (``LinkedIssuanceTransactionMixin`` / ``LinkedPaymentTransactionMixin``
/ ``LinkedRePaymentTransactionMixin``).
"""

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

# -----------------------------
# Mixins
# -----------------------------


class BaseModelMixin:
    """Base for model mixins.

    Provides the ``pk`` / ``all_objects`` type annotations and a plain
    ``save()`` passthrough that concrete mixins chain via ``super()``.
    """

    pk: models.BigAutoField
    all_objects: models.Manager

    def save(self, *args, **kwargs) -> None:
        return super().save(*args, **kwargs)  # type: ignore


class ImmutableMixin(BaseModelMixin):
    """Ensure the save() method will never update immutable fields"""

    _immutable_fields: dict[str, dict] = {}

    @property
    def immutable_field_names(self):
        """Names of the fields this model protects from later mutation."""
        rv = []
        for f in self._immutable_fields:
            rv.append(f if isinstance(f, str) else f[0])
        return rv

    def save(self, *args, **kwargs):
        """Block updates to immutable fields once set, unless permitted.

        ``ALLOW_SET`` / ``NULL_VALUES`` per-field rules may relax the guard for
        explicitly whitelisted transitions.
        """
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
        """Reject amounts that are zero or negative."""
        amount = getattr(
            self, self._amount_name
        )  # don't add default, let the code to fail if the var name is incorrect
        if amount <= 0:
            raise ValidationError(
                _("Amount should be positive, got %(amount)s") % {"amount": amount}
            )
        return super().clean()


class OfficerMixin(BaseModelMixin):
    """Require the linked ``officer`` user to be an active staff member."""

    def clean(self):
        """Require the linked officer to be an active staff user."""
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
        """Net amount after applying active (non-reversed) adjustments."""
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
    """Validate the payment source (payer) fund exists and is active.

    Subclasses implement :attr:`payment_source_fund`; ``clean()`` rejects a
    missing/inactive fund.
    """

    @property
    def payment_source_fund(self):
        raise NotImplementedError()

    def _validate_payment_source_fund_exists(self):
        """Ensure the payment source fund resolves and is active."""
        try:
            if not self.payment_source_fund:
                raise ValidationError(_("Payment source fund is not existing."))
        except Exception:
            raise ValidationError(_("Payment source fund could not be resolved."))
        fund = self.payment_source_fund
        if not fund.active:
            raise ValidationError(_("The Payment source entity should be active."))

    def clean(self) -> None:
        """Validate the payment source fund before saving."""
        self._validate_payment_source_fund_exists()
        return super().clean()


class TargetFundMixin(BaseModelMixin):
    """Validate the payment target (receiver) fund exists and is active.

    Subclasses implement :attr:`payment_target_fund`; ``clean()`` rejects a
    missing/inactive fund.
    """

    @property
    def payment_target_fund(self):
        raise NotImplementedError()

    def _validate_payment_target_fund_exists(self):
        """Ensure the payment target fund resolves and is active."""
        try:
            if not self.payment_target_fund:
                raise ValidationError(_("Payment target fund is not existing."))
        except Exception:
            raise ValidationError(_("Payment target fund could not be resolved."))
        fund = self.payment_target_fund
        if not fund.active:
            raise ValidationError(_("The Payment target entity should be active."))

    def clean(self) -> None:
        """Validate the payment target fund before saving."""
        self._validate_payment_target_fund_exists()
        return super().clean()


class HasRelatedTransactions(BaseModelMixin):
    """Expose the transactions attached to a record via its content type.

    Provides ``get_all_transactions()`` (all rows) and
    ``get_undeleted_transactions()`` (soft-delete aware) querysets.
    """

    _related_transaction_name = "transactions"

    def get_all_transactions(self) -> SafeQuerySet:
        """Return the transactions attached to this record via content type."""
        # Ensure your Transaction model has content_type and object_id fields
        from django.contrib.contenttypes.models import ContentType

        from apps.app_transaction.models import Transaction

        ct = ContentType.objects.get_for_model(self.__class__)
        # Return the QuerySet, don't just execute it!
        return Transaction.objects.filter(content_type=ct, object_id=self.pk)

    def get_undeleted_transactions(self):
        """Return the record's transactions excluding soft-deleted ones."""
        return self.get_all_transactions().filter(deleted_at__isnull=True)

    def _before_soft_delete(self) -> None:
        """Soft-delete this record's ledger transactions with it.

        Transactions attach through a ``GenericForeignKey`` (content_type /
        object_id), so they have no reverse FK for the delete guard to find and
        would otherwise survive as live orphans still referencing the record's
        entities. Reversal mirrors are soft-deleted first so an original is
        never held back by its own still-live reversal.
        """
        txs = self.get_all_transactions()
        ordered = list(txs.filter(reversal_of__isnull=False)) + list(
            txs.filter(reversal_of__isnull=True)
        )
        for tx in ordered:
            tx.delete()


class AutoTransactionMixin(BaseModelMixin):
    """Shared ``save()`` plumbing for mixins that auto-create transactions.

    Concrete subclasses implement ``_schedule_transaction_tasks(kwargs)`` and call
    ``super()._schedule_transaction_tasks(kwargs)`` so composed mixins (e.g. issuance
    + payment in ``TransactionMixin``) each append their own post-save task. Reversal
    records (``reversal_of`` / ``reversed_by``) are counter-documents — they never
    create their own transactions.
    """

    def _is_reversal_record(self) -> bool:
        """True when this record is a reversal counter-document."""
        if getattr(self, "reversal_of", None) is not None and self.reversal_of:
            return True
        if getattr(self, "reversed_by", None) is not None and self.reversed_by:
            return True
        return False

    def _schedule_transaction_tasks(self, kwargs: dict) -> None:
        """Hook for subclasses to append their ``post_save_tasks``. No-op by default."""

    def save(self, *args, **kwargs) -> None:
        """Atomically schedule transaction tasks for new, non-reversal records."""
        with db_transaction.atomic():
            if self.pk is None and not self._is_reversal_record():
                self._schedule_transaction_tasks(kwargs)
            return super().save(*args, **kwargs)


class LinkedIssuanceTransactionMixin(
    SourceFundMixin, TargetFundMixin, HasRelatedTransactions, AutoTransactionMixin
):
    """Auto-create the single issuance transaction when a new record is saved.

    On insert (unless the record is a reversal counter-document) the record's
    configured ``_issuance_transaction_type`` is created between its source and
    target funds.
    """

    _issuance_transaction_type: "TransactionType"

    @property
    def _has_issuance_transaction(self) -> bool:
        """Indicates if this record can/should be linked to a transaction of type *_Issuance"""
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
        from apps.app_audit import context as provenance
        from apps.app_audit import reasons

        with db_transaction.atomic(), provenance.derived(
            reasons.ROLE_ISSUANCE_TXN, reasons.REASON_AUTO_ISSUANCE
        ):
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

    def _schedule_transaction_tasks(self, kwargs: dict) -> None:
        if self._has_issuance_transaction:
            kwargs.setdefault("post_save_tasks", []).append(
                (self.create_issuance_transaction, (), {"date": self.date})
            )
        super()._schedule_transaction_tasks(kwargs)


class LinkedPaymentTransactionMixin(
    SourceFundMixin, TargetFundMixin, HasRelatedTransactions, AutoTransactionMixin
):
    """Adds payment/settlement transactions and the settlement amount API.

    Configuration knobs (class attrs, overridden per proxy):
      * ``_payment_transaction_type`` — TransactionType used for payments.
      * ``max_payment_transaction_count`` — 0 = no payments, 1 = exactly one
        payment (one-shot), -1 = unlimited partial payments.
      * ``_is_one_shot_operation`` — when True the payment fires at creation
        (issuance + a single payment, the spec's E@create) and any later
        payment is blocked.
      * ``check_balance_on_payment`` — lock the payer fund and verify it can
        pay before creating each payment transaction. Set on operations whose
        payer is a real person/project entity; leave False for system/world
        payers or admin correction operations that must never be fund-blocked.
    """

    max_payment_transaction_count = 0
    _is_one_shot_operation = False
    check_balance_on_payment = False
    _payment_transaction_type: "TransactionType"
    _amount_field_name = "amount"

    @property
    def amount_settled(self):
        """Net amount settled: money moved toward the receiver minus refunds.

        Based on valid (non-reversed, non-deleted) payment transactions only.
        """
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
        # We define 'refund' as money moving back to the Payer
        from_receiver = valid_txs.filter(source=self.payment_target_fund).aggregate(
            total=Sum(self._amount_field_name)
        )["total"] or Decimal("0.00")

        return to_receiver - from_receiver

    @property
    def total_settlable_amount(self):
        """Total amount this record is due to settle (effective when available)."""
        if hasattr(self, "effective_amount"):
            return self.effective_amount
        return getattr(self, self._amount_field_name, 0)

    @property
    def amount_remaining_to_settle(self):
        """Amount still owed to reach full settlement."""
        return self.total_settlable_amount - self.amount_settled

    @property
    def is_fully_settled(self) -> bool:
        """True when the settled amount covers the total settlable amount."""
        # Precision check: useful when dealing with floating point math / Decimals
        return self.amount_settled >= self.total_settlable_amount

    @property
    def is_overpayed_settled(self) -> bool:
        """True when more than the settlable amount has been paid."""
        # Precision check: useful when dealing with floating point math / Decimals
        return self.amount_settled > self.total_settlable_amount

    def validate_settlement_amount(self, amount_to_pay: Decimal):
        """Raise unless *amount_to_pay* is positive and within the remaining balance."""
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

    @property
    def payment_transactions(self):
        """Return payment transactions filtered by the payment transaction type."""
        if not self._has_payment_transaction:
            return self.get_all_transactions().none()
        return self.get_all_transactions().filter(type=self._payment_transaction_type)

    def create_payment_transaction(
        self, amount, officer, date, description="", note=""
    ):
        """Create and save a payment transaction toward this record's settlement.

        Runs inside one atomic block, optionally balance-checks and locks the
        payer fund, and enforces one-shot / closed-period / overpayment rules.
        """
        from apps.app_transaction.models import Transaction
        from apps.app_audit import context as provenance
        from apps.app_audit import reasons

        # The whole method runs inside one transaction so the balance check and
        # the payment insert are atomic, and the payer fund row can be locked
        # (SELECT ... FOR UPDATE) to stop concurrent payments both passing the
        # balance check. No-op on backends without row locking (e.g. SQLite).
        with db_transaction.atomic(), provenance.derived(
            reasons.ROLE_PAYMENT_TXN, reasons.REASON_AUTO_PAYMENT
        ):
            # Reject payments dated inside a closed financial period of the
            # operation's governing entity.
            from apps.app_operation.models.period import is_date_in_closed_period

            period_entity = getattr(self, "period_entity", None)
            if period_entity and is_date_in_closed_period(period_entity, date):
                raise ValidationError(
                    _(
                        "Cannot record a payment dated within a closed financial period."
                    )
                )

            if self.check_balance_on_payment:
                fund_model = self.payment_source_fund.__class__
                fund_pk = self.payment_source_fund.pk
                fund = fund_model.objects.select_for_update().get(pk=fund_pk)
                # can_pay() only balance-checks real (non-virtual) internal
                # funds; external and virtual funds are always allowed to pay.
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
                        _(
                            "One-shot operations can only have a single payment transaction."
                        )
                    )
                if amount != self.amount:
                    raise ValidationError(
                        _(
                            "Payment amount %(amount)s must match the operation amount %(op_amount)s."
                        )
                        % {"amount": amount, "op_amount": self.amount}
                    )

            self.validate_settlement_amount(amount)
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

    def _schedule_transaction_tasks(self, kwargs: dict) -> None:
        """Append the auto payment task for one-shot operations on insert."""
        if self._is_one_shot_operation:
            if not self._has_single_payment_transaction:
                raise ValidationError(
                    _("This record can't act as a one-shot operation record")
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
        super()._schedule_transaction_tasks(kwargs)


class LinkedRePaymentTransactionMixin(
    SourceFundMixin, TargetFundMixin, HasRelatedTransactions, BaseModelMixin
):
    """Expose the repayment / remaining-amount API for repayable records.

    Computes how much of a disbursement (e.g. a loan) has been repaid through
    repayment transactions and how much is still owed, bounded by what was
    actually paid out.
    """

    # ################################################
    # Indicates the type of the issuance transaction
    _repayment_transaction_type: "TransactionType"
    _amount_field_name = "amount"
    _tx_amount_field_name = "amount"
    is_repayable = False

    @property
    def total_repayable_amount(self):
        """Total amount that could be repaid (effective when available)."""
        if hasattr(self, "effective_amount"):
            return self.effective_amount
        return getattr(self, self._amount_field_name, Decimal("0.00"))

    @property
    def repayable_amount(self):
        """
        Maximum total that may be repaid: the lesser of the operation total and
        the net amount actually disbursed (the payment transaction sum). This
        enforces the rule that repayments recover only what was really paid out,
        so a loan with no disbursement is not repayable.
        """
        if hasattr(self, "amount_settled"):
            return min(self.total_repayable_amount, self.amount_settled)
        return self.total_repayable_amount

    @property
    def amount_repayed(self):
        """Net amount already repaid back to the payer, net of reversals."""
        # Net-of-reversal approach (mirrors amount_settled): sum money flowing
        # into the source fund (repayments) minus money flowing back out of it
        # (the mirror reversals of reversed repayments). Without the offset term
        # a reversed repayment would keep counting towards the repaid amount.
        valid_txs = self.get_undeleted_transactions()
        if not valid_txs:
            return Decimal("0")
        if hasattr(self, "_repayment_transaction_type"):
            valid_txs = valid_txs.filter(type=self._repayment_transaction_type)
        to_source = valid_txs.filter(target=self.payment_source_fund).aggregate(
            total=Sum(self._tx_amount_field_name)
        )["total"] or Decimal("0.00")
        from_source = valid_txs.filter(source=self.payment_source_fund).aggregate(
            total=Sum(self._tx_amount_field_name)
        )["total"] or Decimal("0.00")
        return to_source - from_source

    @property
    def amount_remaining_to_repay(self):
        """Amount still owed to fully repay."""
        return self.repayable_amount - self.amount_repayed

    @property
    def is_fully_repayed(self) -> bool:
        """True when the repaid amount covers the repayable amount."""
        return self.amount_repayed >= self.repayable_amount

    @property
    def is_overpaid_repayed(self) -> bool:
        """True when more than the repayable amount has been repaid."""
        return self.amount_repayed > self.repayable_amount

    def validate_repayement_amount(self, amount_to_pay: Decimal):
        """Raise unless *amount_to_pay* is positive and within the remaining balance."""
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

    @property
    def repayment_transactions(self):
        """Return repayment transactions filtered by the repayment transaction type."""
        if not self._has_repayment_transaction:
            return self.get_all_transactions().none()
        return self.get_all_transactions().filter(type=self._repayment_transaction_type)

    def create_repayment_transaction(
        self, amount, officer, date, description="", note=""
    ):
        """Create and save a repayment transaction back to the payer.

        Validates the amount and rejects repayments dated inside a closed
        financial period.
        """
        from apps.app_transaction.models import Transaction
        from apps.app_audit import context as provenance
        from apps.app_audit import reasons

        self.validate_repayement_amount(amount)

        with db_transaction.atomic(), provenance.derived(
            reasons.ROLE_REPAYMENT_TXN, reasons.REASON_AUTO_REPAYMENT
        ):
            # Reject repayments dated inside a closed financial period of the
            # operation's governing entity.
            from apps.app_operation.models.period import is_date_in_closed_period

            period_entity = getattr(self, "period_entity", None)
            if period_entity and is_date_in_closed_period(period_entity, date):
                raise ValidationError(
                    _(
                        "Cannot record a repayment dated within a closed financial period."
                    )
                )
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
