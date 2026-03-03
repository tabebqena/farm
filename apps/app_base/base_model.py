from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.db import transaction as db_transaction
from django.forms import ValidationError
from django.utils import timezone

from .managers import ActiveManager, DefaultManager
from .mixins import HasRelatedTransactions

# TODO use database level constrains for dataintegrity.
# TODO add finiancial period closing


# -----------------------------
# Base Model
# -----------------------------
class BaseModel(models.Model):
    id: models.BigAutoField
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, default=None)

    deletable = models.BooleanField(blank=False, null=False, default=False)

    all_objects = DefaultManager  # Default manager
    objects = ActiveManager()  # Custom manager for non-deleted items

    class Meta:
        abstract = True

    def __setattr__(self, name, value):
        # 1. Check if the attribute being changed is 'deletable'
        # 2. Check if the object is already in the DB (has a PK)
        if name == "deletable" and self.pk is not None:
            # Fetch the value currently stored in the object's memory
            # (Using __dict__.get to avoid infinite recursion)
            current_val = self.__dict__.get(name)
            from crum import get_current_user

            # If the value is actually changing
            if current_val is not None and current_val != value:
                user = get_current_user()
                # Block if user is not a superuser
                if not (user and user.is_superuser):
                    raise PermissionDenied(
                        f"Permission Denied: Only superusers can modify the 'deletable' status of {self.__class__.__name__}."
                    )

        super().__setattr__(name, value)

    def save(self, *args, **kwargs):
        self.full_clean()
        is_new = self.pk is None
        if is_new and not isinstance(self.deletable, bool):
            self.deletable = False
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if not self.deletable:
            raise RuntimeError(f"Deletion is strictly blocked for this object")
        from crum import get_current_user

        user = get_current_user()
        if user and user.is_superuser:
            return super().delete(*args, **kwargs)  # Hard delete for superuser
        if not self.deleted_at:
            self.deleted_at = timezone.now()  # Soft delete for others
        return self.save()


class ReversableModel(HasRelatedTransactions, BaseModel):

    reversal_of = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reversed_by",
    )

    @property
    def is_reversed(self):
        return getattr(self, "reversed_by", None) is not None

    @property
    def is_reversal(self):
        return self.reversal_of is not None

    def get_reverse_filtered_out_transaction_types(self):
        """returns a list of all transaction taypes that should
        be filtered out during the reversal process, this types are usually the creation transaction as they
        should exist before the reversal."""
        raise NotImplementedError()

    def _validate_requires_not_reversed(self):
        if self.is_reversed:
            raise ValidationError(f"This invoice is reversed by  {self.reversed_by}.")

    def _validate_requires_not_reversal(self):
        if self.is_reversal:
            raise ValidationError("This invoice is a reversal.")

    def _validate_can_be_reversed(self):
        if self.reversal_of is not None:
            raise ValidationError(
                "You can't reverse this transaction as it is arefersal of another transaction {self.reversal_of}."
            )

        if getattr(self, "reversed_by", None) is not None:
            # TODO: correct the error msg
            raise ValidationError("The transaction is already reversed.")

    def reverse(self, officer, date=None, reason="reversal"):
        self._validate_can_be_reversed()
        date = date or timezone.now()
        # Identify related transactions (payments/collections/transactions)
        all_txs = self.get_valid_transactions()
        filtered = self.get_reverse_filtered_out_transaction_types()
        if filtered:
            all_txs_excecpt_filtered = (
                all_txs.exclude(type__in=filtered) if all_txs else None
            )
            filtered_out_transactions = (
                all_txs.filter(type__in=filtered) if all_txs else None
            )
        else:
            all_txs_excecpt_filtered = all_txs
            filtered_out_transactions = all_txs

        if all_txs_excecpt_filtered and all_txs_excecpt_filtered.count() > 0:
            raise ValidationError(
                "You can't reverse this object as it has non-reversed transactions"
                " To continue, you should manually reverse all the related transactions"
            )

        if hasattr(self, "adjustments"):
            adjs = self.adjustments.filter(  # type:ignore
                deleted_at__isnull=True,
                reversed_by__isnull=True,
            ).all()
            if len(adjs) > 0:
                raise ValidationError(
                    "You can't reverse this object as it has non-reversed adjustments"
                    " To continue, you should manually reverse all of them"
                )
        if filtered_out_transactions:
            for tx in filtered_out_transactions.all():
                tx.reverse(officer=officer)

        # We clone the object and link it back via reversal_of
        with db_transaction.atomic():
            counter_record = self.__class__.objects.get(pk=self.pk)
            counter_record.pk = None
            counter_record.reversal_of = self
            counter_record.officer = officer
            counter_record.reason = reason
            counter_record.date = date or timezone.now()
            counter_record.description = f"the record {self.id} has been successfult reversed."  # type: ignore
            counter_record.save()

            self.reversed_by = counter_record
            self.save()

            return counter_record

    class Meta:
        abstract = True
