import typing
from typing import Collection, List

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.db import transaction as db_transaction
from django.db.models.expressions import DatabaseDefault
from django.forms import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

if typing.TYPE_CHECKING:
    from apps.app_transaction.transaction_type import TransactionType

from django import conf

from .managers import ActiveManager, DefaultManager
from .mixins import HasRelatedTransactions

# TODO use database level constrains for dataintegrity.
# TODO add finiancial period closing


# -----------------------------
# Base Model
# -----------------------------
class BaseModel(models.Model):
    id: models.BigAutoField
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    deleted_at = models.DateTimeField(
        _("deleted at"), null=True, blank=True, default=None
    )

    deletable = models.BooleanField(
        _("deletable"), blank=False, null=False, default=False
    )

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
                        _(
                            "Permission Denied: Only superusers can modify the 'deletable' status of %(class_name)s."
                        )
                        % {"class_name": self.__class__.__name__}
                    )

        super().__setattr__(name, value)

    def clean_fields(self, exclude: Collection[str] | None = None) -> None:
        """
        Overridden to simulate forms.clean{field_name} Clean all fields and raise a ValidationError containing a dict
        of all validation errors if any occur.
        """
        if exclude is None:
            exclude = set()

        errors = {}
        for f in self._meta.fields:
            if f.name in exclude or f.generated:
                continue
            # Skip validation for empty fields with blank=True. The developer
            # is responsible for making sure they have a valid value.
            raw_value = getattr(self, f.attname)
            if f.blank and raw_value in f.empty_values:
                continue
            # Skip validation for empty fields when db_default is used.
            if isinstance(raw_value, DatabaseDefault):
                continue
            try:
                if getattr(self, f"clean_{f.name}", None) is not None:
                    getattr(self, f"clean_{f.name}")()
            except ValidationError as e:
                errors[f.name] = e.error_list

        if errors:
            raise ValidationError(errors)

        return super().clean_fields(exclude)

    def post_save(self, post_save_tasks):
        for f, f_args, f_kwargs in post_save_tasks:
            f(*f_args, **f_kwargs)

    def save(self, *args, **kwargs):
        self.full_clean()
        is_new = self.pk is None
        if is_new and not isinstance(self.deletable, bool):
            self.deletable = False
        rv = super().save(
            force_insert=kwargs.get("force_insert", False),
            force_update=kwargs.get("force_update", False),
            using=kwargs.get("using", None),
            update_fields=kwargs.get("update_fields", None),
        )

        self.post_save(kwargs.get("post_save_tasks", []))
        return rv

    def delete(self, *args, **kwargs):
        if conf.settings.DEBUG:
            return super().delete(*args, **kwargs)
        if not self.deletable:
            raise RuntimeError(_("Deletion is strictly blocked for this object"))
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
        verbose_name=_("reversal of"),
    )

    @property
    def is_reversed(self) -> bool:
        return getattr(self, "reversed_by", None) is not None

    @property
    def is_reversal(self) -> bool:
        return getattr(self, "reversal_of", None) is not None

    def _get_issuance_transaction_type(self):
        """returns the issuance transaction type."""
        return getattr(self, "_issuance_transaction_type", None)

    def _get_payment_transaction_type(self):
        """returns the payment transaction type."""
        return getattr(self, "_payment_transaction_type", None)

    def _validate_requires_not_reversed(self):
        if self.is_reversed:
            raise ValidationError(
                _("This invoice is reversed by %(reversed_by)s.")
                % {"reversed_by": self.reversed_by}
            )

    def _validate_requires_not_reversal(self):
        if self.is_reversal:
            raise ValidationError(_("This invoice is a reversal."))

    def _validate_can_be_reversed(self):
        if self.reversal_of is not None:
            raise ValidationError(
                _(
                    "You can't reverse this record as it is a reversal of %(reversal_of)s."
                )
                % {"reversal_of": self.reversal_of}
            )

        if getattr(self, "reversed_by", None) is not None:
            # TODO: correct the error msg
            raise ValidationError(_("The transaction is already reversed."))

    def _get_reverse_kwargs(self, **overwrite):
        fields = self._meta.concrete_fields
        kwargs = {}

        for field in fields:
            if field.primary_key:
                continue
            name = field.name

            if name in overwrite:
                kwargs[name] = overwrite[name]
            elif getattr(self, f"_reverse_{name}", None) is not None:
                kwargs[name] = getattr(self, f"_reverse_{name}")()
            else:
                kwargs[name] = getattr(self, name, None)
        kwargs["reversal_of"] = self
        kwargs["pk"] = None
        return kwargs

    def _requires_transaction_reversal(self, all_txs: models.QuerySet) -> bool:
        # All transactions that are reversable and
        # should be explicity reversed
        # by the user before reversing thier document
        explicit_reversing_transactions = all_txs.filter(
            type__in=self._reversable_transaction_types
        ).exclude(type__in=self._implicit_reversable_transaction_types)

        if explicit_reversing_transactions.count() > 0:
            return True

        return False

    @property
    def _reversable_transaction_types(self) -> List["TransactionType"]:
        """returns a list of transaction types that should be reversed
        during the reverse process of this document.
        Default all payment transactions of this document are reversable
        """
        payment = self._get_payment_transaction_type()
        if payment:
            return [payment]
        return []

    @property
    def _implicit_reversable_transaction_types(self) -> List["TransactionType"]:
        """returns a list of transaction that can be implicity reversed during this object
        reversal. Any transaction not listed here, should be explicity reversed by the user.
        Default: The user should reverse all transactions explicity.
        """
        return []

    def reverse(self, officer, date=None, reason=None):
        self._validate_can_be_reversed()
        date = date or timezone.now()
        # Identify related transactions (payments/collections/transactions)
        all_txs = self.get_all_transactions()
        if self._requires_transaction_reversal(all_txs):
            raise ValidationError(
                _(
                    "You can't reverse this object as it has non-reversed transactions. "
                    "To continue, you should manually reverse all the related transactions."
                )
            )

        if hasattr(self, "adjustments"):
            adjs = self.adjustments.filter(  # type:ignore
                deleted_at__isnull=True,
                reversed_by__isnull=True,
            ).all()
            if len(adjs) > 0:
                raise ValidationError(
                    _(
                        "You can't reverse this object as it has non-reversed adjustments. To continue, you should manually reverse all of them."
                    )
                )
        for tx in all_txs.filter(type__in=self._reversable_transaction_types).all():
            if not tx.is_reversal and not tx.is_reversed:
                tx.reverse(officer=officer)
        kwargs = self._get_reverse_kwargs(
            officer=officer,
            date=date or timezone.now(),
            description=reason
            or _("reversal of %(model)s (%(pk)s)")
            % {"model": self.__class__.__name__, "pk": self.pk},
        )
        # We clone the object and link it back via reversal_of
        with db_transaction.atomic():
            reversal_record = self.__class__(**kwargs)
            reversal_record.save()
            self.reversed_by = reversal_record
            return reversal_record

    def save(self, *args, **kwargs) -> None:
        return super().save(*args, **kwargs)

    class Meta:
        abstract = True
