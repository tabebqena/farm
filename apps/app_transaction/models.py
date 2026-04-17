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
        if self.source == self.target:
            raise ValidationError("Source and target funds must be different.")
        # if self.content_type:
        #     model_name = self.content_type.model  # lowercase model name

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
        violation = tx_type.get_entity_type_violation(source, target)
        if violation:
            raise ValidationError(
                f"Transaction type '{tx_type}' has invalid entity types: {violation}."
            )
        if not tx_type.is_allowed_operation_type(document):
            raise ValidationError(
                f"Transaction type '{tx_type}' is not allowed for operation '{type(document).__name__}'."
            )
        resolved_date = date or timezone.now()
        if isinstance(resolved_date, datetime.date) and not isinstance(
            resolved_date, datetime.datetime
        ):
            resolved_date = timezone.make_aware(
                datetime.datetime.combine(resolved_date, datetime.time.min)
            )
        return Transaction.objects.create(
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
        resolved_date = date or timezone.now()
        if isinstance(resolved_date, datetime.date) and not isinstance(
            resolved_date, datetime.datetime
        ):
            resolved_date = timezone.make_aware(
                datetime.datetime.combine(resolved_date, datetime.time.min)
            )
        reversal = Transaction(
            date=resolved_date,
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
