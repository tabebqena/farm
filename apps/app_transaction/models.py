import datetime
import logging
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

from apps.app_base.debug import DebugContext, debug_transaction
from apps.app_base.mixins import AmountCleanMixin, ImmutableMixin
from apps.app_base.models import BaseModel
from apps.app_transaction.transaction_type import TransactionType

logger = logging.getLogger(__name__)

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
        DebugContext.log(f"Transaction.clean()", {
            "type": self.type,
            "source": str(self.source),
            "target": str(self.target),
            "amount": float(self.amount),
        })
        if self.source == self.target:
            DebugContext.error("Source and target are the same", data={
                "source": str(self.source),
                "target": str(self.target),
            })
            raise ValidationError("Source and target funds must be different.")
        DebugContext.success("Transaction validation passed")
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
        with DebugContext.section(f"Transaction.create()", {
            "type": str(tx_type),
            "source": str(source),
            "target": str(target),
            "amount": float(amount),
            "document_type": type(document).__name__,
            "document_pk": getattr(document, "pk", None),
        }):
            DebugContext.log("Validating entity types")
            violation = tx_type.get_entity_type_violation(source, target)
            if violation:
                DebugContext.error("Entity type violation", data={
                    "type": str(tx_type),
                    "violation": violation,
                })
                raise ValidationError(
                    f"Transaction type '{tx_type}' has invalid entity types: {violation}."
                )
            DebugContext.success("Entity types valid")

            DebugContext.log("Validating operation type")
            if not tx_type.is_allowed_operation_type(document):
                DebugContext.error("Operation type not allowed", data={
                    "type": str(tx_type),
                    "operation_type": type(document).__name__,
                })
                raise ValidationError(
                    f"Transaction type '{tx_type}' is not allowed for operation '{type(document).__name__}'."
                )
            DebugContext.success("Operation type valid")

            DebugContext.log("Resolving transaction date")
            resolved_date = date or timezone.now()
            if isinstance(resolved_date, datetime.date) and not isinstance(
                resolved_date, datetime.datetime
            ):
                resolved_date = timezone.make_aware(
                    datetime.datetime.combine(resolved_date, datetime.time.min)
                )
            DebugContext.log("Date resolved", {"date": str(resolved_date)})

            DebugContext.log("Creating Transaction record in database")
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
            DebugContext.success("Transaction created", {"transaction_pk": tx.pk})

            # Audit log the transaction creation
            DebugContext.audit(
                action="transaction_created",
                entity_type="Transaction",
                entity_id=tx.pk,
                details={
                    "type": str(tx_type),
                    "amount": float(amount),
                    "source": str(source),
                    "target": str(target),
                    "document": str(document),
                },
                user=str(officer or document.officer)
            )
            return tx

    @db_transaction.atomic
    def reverse(self, officer, reason="", date=None):
        """
        Creates a counter-transaction to neutralize this transaction.
        """
        import uuid
        txn_id = f"reverse_txn_{self.pk}_{uuid.uuid4().hex[:8]}"
        DebugContext.transaction_start(txn_id, f"Reversing transaction {self.pk}", {
            "original_txn_pk": self.pk,
            "type": self.type,
            "amount": float(self.amount),
            "officer": str(officer),
            "reason": reason,
        })

        DebugContext.log(f"Transaction.reverse() called", {
            "transaction_pk": self.pk,
            "type": self.type,
            "amount": float(self.amount),
            "officer": str(officer),
            "reason": reason,
        })

        try:
            if self.reversal_of:
                DebugContext.error("Cannot reverse a reversal", data={
                    "transaction_pk": self.pk,
                    "reversal_of_pk": self.reversal_of_id,
                })
                raise ValidationError(
                    "Cannot reverse a transaction that is already a reversal."
                )

            if hasattr(self, "reversed_by") and self.reversed_by:  # type: ignore
                DebugContext.error("Transaction already reversed", data={
                    "transaction_pk": self.pk,
                    "reversed_by_pk": self.reversed_by.pk,
                })
                raise ValidationError("This transaction has already been reversed.")
        except Exception as e:
            DebugContext.transaction_rollback(txn_id, str(e), e)
            DebugContext.audit(
                action="transaction_reversal_failed",
                entity_type="Transaction",
                entity_id=self.pk,
                details={"error": str(e), "reason": reason},
                user=str(officer)
            )
            raise

        with DebugContext.section(f"Creating reversal transaction", {
            "original_transaction_pk": self.pk,
            "original_source": str(self.source),
            "original_target": str(self.target),
            "reversal_source": str(self.target),  # Swapped
            "reversal_target": str(self.source),  # Swapped
            "amount": float(self.amount),
        }):
            DebugContext.log("Resolving reversal date")
            resolved_date = date or timezone.now()
            if isinstance(resolved_date, datetime.date) and not isinstance(
                resolved_date, datetime.datetime
            ):
                resolved_date = timezone.make_aware(
                    datetime.datetime.combine(resolved_date, datetime.time.min)
                )

            DebugContext.log("Creating mirror-image transaction")
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
            DebugContext.success("Reversal transaction created", {"reversal_pk": reversal.pk})

            setattr(self, "reversed_by", reversal)
            DebugContext.success("Reversal linked to original transaction")

            # Commit the transaction and log audit trail
            DebugContext.transaction_commit(txn_id, {
                "original_txn_pk": self.pk,
                "reversal_txn_pk": reversal.pk,
                "status": "success"
            })

            DebugContext.audit(
                action="transaction_reversed",
                entity_type="Transaction",
                entity_id=self.pk,
                details={
                    "reversal_pk": reversal.pk,
                    "reason": reason,
                    "original_amount": float(self.amount),
                },
                user=str(officer)
            )

            return reversal

    def get_absolute_url(self):
        return reverse("transaction_detail", kwargs={"transaction_pk": self.pk})
