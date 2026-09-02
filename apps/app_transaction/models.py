"""Transaction model.

Defines :class:`Transaction`, the immutable ledger record that moves money (or
creates an obligation) between a source and a target fund for a given
:class:`~apps.app_transaction.transaction_type.TransactionType`. It supports
generic linking back to the owning document (operation / adjustment), provides
factory creation helpers and can be reversed by an officer.
"""

import datetime
import typing
from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.db import transaction as db_transaction
from django.forms import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.app_base.logging_utils import audit_logger, logger
from apps.app_base.mixins import AmountCleanMixin, ImmutableMixin
from apps.app_base.models import BaseModel
from apps.app_transaction.transaction_type import TransactionType

if typing.TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser

    from apps.app_entity.models import Entity
# TODO use database level constrains for dataintegrity.
# TODO add finiancial period closing
# TODO : "Financial Statement" method
# TODO: Integrity check method


class Transaction(AmountCleanMixin, ImmutableMixin, BaseModel):
    _immutable_fields = {
        "source": {},
        "target": {},
        "type": {},
        "amount": {},
        "officer": {},
        "reversal_of": {"ALLOW_SET": True},
    }
    date = models.DateTimeField(default=timezone.now)
    # source is the fund that gives the amount.
    source = models.ForeignKey(
        "app_entity.Entity",
        on_delete=models.PROTECT,
        related_name="transactions_outgoing",
        blank=False,
        null=False,
    )
    # target is the fund that receives the amount.
    target = models.ForeignKey(
        "app_entity.Entity",
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
        settings.AUTH_USER_MODEL,
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

    def clean_type(self, **kwargs): ...

    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)

    def clean(self) -> None:
        logger.debug(
            f"Transaction.clean() | type={self.type} | source={self.source} | "
            f"target={self.target} | amount={float(self.amount)}"
        )
        if self.source == self.target:
            logger.error(
                f"Source and target are the same | source={self.source} | "
                f"target={self.target}"
            )
            raise ValidationError("Source and target funds must be different.")
        logger.debug("Transaction validation passed")
        return super().clean()

    @staticmethod
    def create(
        source: "Entity",
        target: "Entity",
        document,
        tx_type: TransactionType,
        amount: Decimal,
        officer: "AbstractBaseUser",
        description="",
        note="",
        date=None,
    ):
        logger.debug(
            f"Transaction.create() | type={tx_type} | source={source} | target={target} | "
            f"amount={float(amount)} | document_type={type(document).__name__} | "
            f"document_pk={getattr(document, 'pk', None)}"
        )

        logger.debug("Validating entity types")
        violation = tx_type.get_entity_type_violation(source, target)
        if violation:
            logger.error(
                f"Entity type violation | type={tx_type} | violation={violation}"
            )
            raise ValidationError(
                f"Transaction type '{tx_type}' has invalid entity types: {violation}."
            )
        logger.debug("Entity types valid")

        logger.debug("Validating operation type")
        if not tx_type.is_allowed_operation_type(document):
            logger.error(
                f"Operation type not allowed | type={tx_type} | "
                f"operation_type={type(document).__name__}"
            )
            raise ValidationError(
                f"Transaction type '{tx_type}' is not allowed for operation '{type(document).__name__}'."
            )
        logger.debug("Operation type valid")

        logger.debug("Resolving transaction date")
        resolved_date = date or timezone.now()
        if isinstance(resolved_date, datetime.date) and not isinstance(
            resolved_date, datetime.datetime
        ):
            resolved_date = timezone.make_aware(
                datetime.datetime.combine(resolved_date, datetime.time.min)
            )
        logger.debug(f"Date resolved | date={resolved_date}")

        logger.debug("Creating Transaction record in database")
        tx = Transaction.objects.create(
            source=source,
            target=target,
            type=tx_type,
            document=document,
            amount=Decimal(str(amount)) if not isinstance(amount, Decimal) else amount,
            officer=officer or document.officer,
            description=description or f"Transaction for {document.description}",
            note=note,
            date=resolved_date,
        )
        logger.debug(f"Transaction created | transaction_pk={tx.pk}")

        # Audit log the transaction creation
        audit_logger.info(
            f"transaction_created | Transaction:{tx.pk} | "
            f"user={officer or document.officer} | "
            f"type={tx_type} | amount={float(amount)} | source={source} | "
            f"target={target} | document={document}"
        )
        return tx

    @db_transaction.atomic
    def reverse(self, officer, reason="", date=None):
        """
        Creates a counter-transaction to neutralize this transaction.
        """
        import uuid
        txn_id = f"reverse_txn_{self.pk}_{uuid.uuid4().hex[:8]}"
        audit_logger.info(
            f"transaction_start | reverse_txn={txn_id} | reversing Transaction:{self.pk} | "
            f"type={self.type} | amount={float(self.amount)} | officer={officer} | "
            f"reason={reason}"
        )

        logger.debug(
            f"Transaction.reverse() called | transaction_pk={self.pk} | type={self.type} | "
            f"amount={float(self.amount)} | officer={officer} | reason={reason}"
        )

        try:
            if self.reversal_of:
                logger.error(
                    f"Cannot reverse a reversal | transaction_pk={self.pk} | "
                    f"reversal_of_pk={self.reversal_of_id}"
                )
                raise ValidationError(
                    "Cannot reverse a transaction that is already a reversal."
                )

            if hasattr(self, "reversed_by") and self.reversed_by:  # type: ignore
                logger.error(
                    f"Transaction already reversed | transaction_pk={self.pk} | "
                    f"reversed_by_pk={self.reversed_by.pk}"
                )
                raise ValidationError("This transaction has already been reversed.")
        except Exception as e:
            audit_logger.error(
                f"transaction_reversal_failed | Transaction:{self.pk} | user={officer} | "
                f"error={e} | reason={reason}"
            )
            raise

        logger.debug("Creating reversal transaction")
        resolved_date = date or timezone.now()
        if isinstance(resolved_date, datetime.date) and not isinstance(
            resolved_date, datetime.datetime
        ):
            resolved_date = timezone.make_aware(
                datetime.datetime.combine(resolved_date, datetime.time.min)
            )

        logger.debug("Creating mirror-image transaction")
        reversal = Transaction(
            date=resolved_date,
            source=self.target,
            target=self.source,
            amount=self.amount,
            type=self.type,
            officer=officer,
            reversal_of=self,
            description=f"REVERSAL of ID {self.id}: {reason}",
            content_type=self.content_type,
            object_id=self.object_id,
            document=self.document,
        )
        reversal.save()
        logger.debug(f"Reversal transaction created | reversal_pk={reversal.pk}")

        setattr(self, "reversed_by", reversal)
        logger.debug("Reversal linked to original transaction")

        audit_logger.info(
            f"transaction_commit | reverse_txn={txn_id} | original_txn={self.pk} | "
            f"reversal_txn={reversal.pk} | status=success"
        )
        audit_logger.info(
            f"transaction_reversed | Transaction:{self.pk} | user={officer} | "
            f"reversal_pk={reversal.pk} | reason={reason} | "
            f"original_amount={float(self.amount)}"
        )

        return reversal

    def get_absolute_url(self):
        return reverse("transaction_detail", kwargs={"transaction_pk": self.pk})
