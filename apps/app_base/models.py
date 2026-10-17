"""Shared base model classes used across every app.

:class:`BaseModel` provides the common ``id`` plus ``created_at`` / ``updated_at``
audit fields and soft-delete support via ``deleted_at``. :class:`ReversableModel`
extends it for records that an officer can reverse, guarding the original record
against mutation and coordinating the reversal of its related transactions.
"""

import re
import typing
from typing import Collection, List

from django.core.exceptions import ValidationError
from django.db import models
from django.db import transaction as db_transaction
from django.db.models.expressions import DatabaseDefault
from django.forms import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

if typing.TYPE_CHECKING:
    from apps.app_transaction.transaction_type import TransactionType

from .logging_utils import audit_logger, logger
from .managers import ActiveManager, DefaultManager
from .mixins import HasRelatedTransactions

# TODO use database level constrains for dataintegrity.
# TODO add finiancial period closing


# Field names that make a record identifiable in the central delete log.
# ``BaseModel.delete()`` includes whichever of these the concrete model exposes
# so the audit line keeps the context the old per-model ``delete()`` overrides
# used to add (operation type/amount/source/destination, contact
# type/value/entity, stakeholder parent/target/role, product
# template/quantity/status, ...). FK targets render through their ``str()``
# (names / usernames) so the line stays flat and greppable.
_DELETE_LOG_CONTEXT_FIELDS = (
    "name",
    "label",
    "value",
    "contact_type",
    "entity",
    "parent",
    "target",
    "role",
    "operation",
    "operation_type",
    "type",
    "source",
    "destination",
    "amount",
    "officer",
    "product_template",
    "quantity",
    "status",
    "active",
)

# Keys ``(model label, pk)`` currently being soft-deleted, so a re-entrant
# delete triggered through the ``_delete_auto_relations`` cascade cannot loop.
_DELETE_IN_PROGRESS: typing.Set[typing.Tuple[str, int]] = set()


def _camel_to_snake(name: str) -> str:
    """Convert a CamelCase class name into a snake_case audit event token.

    ``ContactInfo`` -> ``contact_info``, ``Operation`` -> ``operation``.
    """
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


# -----------------------------
# Base Model
# -----------------------------
class BaseModel(models.Model):
    """Abstract base model shared by every record in the project.

    Provides the common ``id`` plus the ``created_at`` / ``updated_at`` audit
    timestamps, soft-delete support via ``deleted_at``, and full validation on
    every ``save()``. ``delete()`` always soft-deletes: it stamps ``deleted_at``
    and re-saves, so rows are never physically removed.
    """

    id: models.BigAutoField
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    deleted_at = models.DateTimeField(
        _("deleted at"), null=True, blank=True, default=None
    )

    all_objects = DefaultManager  # Default manager
    objects = ActiveManager()  # Custom manager for non-deleted items

    # --- Soft-delete guard configuration (override per concrete model) ---- #
    # Reverse relation accessor names whose live dependents are AUTO
    # soft-deleted when this record is deleted, and which are therefore
    # excluded from the deletion guard. Used to break circular dependencies
    # (A references B and B references A): declare the side that may cascade.
    _delete_auto_relations: typing.Tuple[str, ...] = ()
    # Reverse relation accessor names to ignore entirely in the guard (neither
    # block nor auto-delete). Reserved for references the caller intentionally
    # leaves behind.
    _delete_guard_ignore_relations: typing.Tuple[str, ...] = ()

    class Meta:
        abstract = True

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
        """Run the queued post-save tasks after a successful ``save()``."""
        for f, f_args, f_kwargs in post_save_tasks:
            f(*f_args, **f_kwargs)

    def save(self, *args, **kwargs):
        """Full-validate, then run post-save tasks, recording the write."""
        self.full_clean()
        provenance_kind = kwargs.pop("provenance_kind", None)
        kind = provenance_kind or ("create" if self._state.adding else "update")
        rv = super().save(
            force_insert=kwargs.get("force_insert", False),
            force_update=kwargs.get("force_update", False),
            using=kwargs.get("using", None),
            update_fields=kwargs.get("update_fields", None),
        )

        self._record_provenance(kind)
        self.post_save(kwargs.get("post_save_tasks", []))
        return rv

    def _record_provenance(self, kind):
        """Record this save in the audit trail (no-op when tracking is off).

        Delegates to :mod:`apps.app_audit.context`; the provenance layer never
        raises into the write it observes.
        """
        try:
            from apps.app_audit import context as provenance

            provenance.record_save(self, kind)
        except Exception:  # pragma: no cover - defensive; must never break save
            logger.exception("provenance: failed to record save for %s", self)

    # ------------------------------------------------------------------ #
    # Soft-delete guard (mirror of DB PROTECT)
    # ------------------------------------------------------------------ #

    def get_delete_blockers(self) -> List[str]:
        """Human labels of live dependent records that must be removed first.

        Considers every reverse FK / one-to-one relation whose child FK
        ``on_delete`` is CASCADE/PROTECT (not SET_NULL / SET_DEFAULT) and that
        is not declared in ``_delete_auto_relations`` or
        ``_delete_guard_ignore_relations``. Dependents that are already
        soft-deleted are ignored, so a parent becomes deletable once its live
        children are removed (leaf-up). Returns ``[]`` when nothing blocks.
        """
        live_by_model: typing.Dict[typing.Any, typing.Set[int]] = {}
        for field in self._dependent_relations():
            child = field.related_model
            pks = set(self._live_dependents_qs(field).values_list("pk", flat=True))
            if pks:
                live_by_model.setdefault(child, set()).update(pks)

        blockers = []
        for child in sorted(live_by_model, key=lambda m: m._meta.label_lower):
            count = len(live_by_model[child])
            label = (
                child._meta.verbose_name
                if count == 1
                else child._meta.verbose_name_plural
            )
            blockers.append(f"{count} {label}")
        return blockers

    def _dependent_relations(self):
        """Yield the reverse FK / one-to-one relations that represent dependents.

        Skipped: auto-created many-to-many join tables (they cannot be
        soft-deleted individually) and relations the model opted out of via
        ``_delete_auto_relations`` / ``_delete_guard_ignore_relations``.
        """
        for field in self._meta.get_fields():
            if not (field.is_relation and field.auto_created):
                continue
            if not (field.one_to_many or field.one_to_one):
                continue
            if self._rel_on_delete(field) in (
                models.SET_NULL,
                models.SET_DEFAULT,
                models.DO_NOTHING,
            ):
                continue
            accessor = field.get_accessor_name()
            if (
                accessor in self._delete_auto_relations
                or accessor in self._delete_guard_ignore_relations
            ):
                continue
            yield field

    @staticmethod
    def _rel_on_delete(field):
        """Resolve the child FK's ``on_delete`` from a reverse relation field."""
        fwd = getattr(field, "field", None)
        if fwd is None or getattr(fwd, "remote_field", None) is None:
            return None
        return getattr(fwd.remote_field, "on_delete", None)

    def _live_dependents_qs(self, field):
        """Queryset of this parent's *live* children behind *field*."""
        child = field.related_model
        fwd = getattr(field, "field", None)
        if fwd is None:
            return child._default_manager.none()
        qs = child._default_manager.filter(**{fwd.name: self})
        if hasattr(child, "deleted_at"):
            qs = qs.filter(deleted_at__isnull=True)
        return qs

    def _auto_soft_delete_dependents(self) -> None:
        """Soft-delete dependents declared in ``_delete_auto_relations``."""
        for accessor in self._delete_auto_relations:
            try:
                field = self._meta.get_field(accessor)
            except Exception:
                # Unknown / renamed relation: skip it.
                continue
            if not (
                field.is_relation
                and field.auto_created
                and (field.one_to_many or field.one_to_one)
            ):
                continue
            for obj in list(self._live_dependents_qs(field)):
                obj.delete()

    def _before_soft_delete(self) -> None:
        """Hook for owned dependents the guard/reverse-relation scan cannot see.

        Runs after the guard has passed and after ``_auto_soft_delete_dependents``,
        immediately before the soft delete. The default is a no-op; concrete
        models override it for children linked through a generic relation (e.g.
        an :class:`~apps.app_operation.models.operation.Operation`'s ledger
        transactions), which have no reverse FK for the guard to discover.
        """

    def delete(self, *args, **kwargs):
        """Soft-delete this record by stamping ``deleted_at`` and re-saving.

        Every record is soft-deleted — nothing is ever physically removed — so
        the audit trail stays intact and the row can be restored later by
        clearing ``deleted_at`` and saving again. Re-saving runs the normal
        ``full_clean()`` validation and post-save hooks.

        Before deleting, a parent is guarded against still having live
        dependents (mirroring the DB-level ``PROTECT``): deleting raises a
        ``ValidationError`` that names what to delete (or reverse) first.
        Dependents listed in ``_delete_auto_relations`` are soft-deleted
        automatically instead of blocking, so a model can declare which side of
        a circular reference may cascade. ``_before_soft_delete()`` then runs as
        a final hook for owned children linked without a reverse FK (e.g. an
        operation's generic transactions). Deletion is logged centrally here on
        both channels: a warning on the project logger and a flat, greppable
        line on the audit channel.
        """
        if self.pk is None or self.deleted_at:
            # Not persisted yet, or already soft-deleted: keep the idempotent
            # path (no guard — nothing new can be orphaned).
            return self._perform_soft_delete(*args, **kwargs)

        key = (self._meta.label_lower, self.pk)
        with db_transaction.atomic():
            if key in _DELETE_IN_PROGRESS:
                # Re-entrant delete caused by the auto-delete cascade: this
                # record is already being removed higher up the stack.
                return None
            _DELETE_IN_PROGRESS.add(key)
            try:
                blockers = self.get_delete_blockers()
                if blockers:
                    raise ValidationError(
                        _(
                            "%(model)s cannot be deleted because the following "
                            "records still reference it; delete (or reverse) "
                            "them first: %(dependents)s."
                        )
                        % {
                            "model": self._meta.verbose_name
                            or type(self).__name__,
                            "dependents": ", ".join(blockers),
                        },
                        code="delete_blocked",
                    )
                self._auto_soft_delete_dependents()
                self._before_soft_delete()
                return self._perform_soft_delete(*args, **kwargs)
            finally:
                _DELETE_IN_PROGRESS.discard(key)

    def _perform_soft_delete(self, *args, **kwargs):
        """Stamp ``deleted_at``, log centrally, and re-save (the soft delete)."""
        if not self.deleted_at:
            self.deleted_at = timezone.now()

        concrete = self._meta.concrete_model or type(self)
        concrete_name = concrete.__name__
        context = self._delete_log_context()
        deleted_at = self.deleted_at.isoformat() if self.deleted_at else ""

        logger.warning(
            f"Deleting {concrete_name} | pk={self.pk} | "
            f"deleted_at={deleted_at} | {context}"
        )
        audit_logger.info(
            f"{_camel_to_snake(concrete_name)}_deleted | "
            f"{concrete_name}:{self.pk} | user=system | "
            f"deleted_at={deleted_at} | {context}"
        )

        return self.save(*args, provenance_kind="soft_delete", **kwargs)

    def _delete_log_context(self) -> str:
        """Build the flat ``key=value`` context for the central delete log.

        Includes only the attributes from ``_DELETE_LOG_CONTEXT_FIELDS`` that
        the concrete model actually exposes and that hold a value; FK targets
        are rendered through ``str()``. Never raises — a logging helper must
        not prevent the soft-delete itself.
        """
        parts = []
        for attr in _DELETE_LOG_CONTEXT_FIELDS:
            if not hasattr(self, attr):
                continue
            try:
                value = getattr(self, attr)
            except Exception:
                continue
            if value is None or value == "" or callable(value):
                continue
            parts.append(f"{attr}={value}")
        return " | ".join(parts)


class ReversableModel(HasRelatedTransactions, BaseModel):
    """Abstract base for records that an officer can reverse.

    Ties the record to its counterpart through ``reversal_of`` / ``reversed_by``
    and provides the reversal guards plus the generic ``reverse()`` that creates
    a mirror record and reverses its related transactions.
    """

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
        """True when this record already has a reversal counter-document."""
        return getattr(self, "reversed_by", None) is not None

    @property
    def is_reversal(self) -> bool:
        """True when this record is itself a reversal counter-document."""
        return getattr(self, "reversal_of", None) is not None

    def _get_issuance_transaction_type(self):
        """returns the issuance transaction type."""
        return getattr(self, "_issuance_transaction_type", None)

    def _get_payment_transaction_type(self):
        """returns the payment transaction type."""
        return getattr(self, "_payment_transaction_type", None)

    def _validate_requires_not_reversed(self):
        """Raise if this record has already been reversed."""
        if self.is_reversed:
            raise ValidationError(
                _("This invoice is reversed by %(reversed_by)s.")
                % {"reversed_by": self.reversed_by}
            )

    def _validate_requires_not_reversal(self):
        """Raise if this record is itself a reversal counter-document."""
        if self.is_reversal:
            raise ValidationError(_("This invoice is a reversal."))

    def _validate_can_be_reversed(self):
        """Raise unless this record may be reversed (not a reversal, not reversed)."""
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
        """Build the field kwargs for a mirror record, honouring ``_reverse_*`` hooks."""
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
        """True when active explicit transactions still block the reversal."""
        # All transactions that are reversable and
        # should be explicity reversed
        # by the user before reversing thier document.
        # Only *active* explicit transactions block reversal: a transaction that
        # has already been reversed (its counter-transaction exists) or a
        # reversal (mirror) transaction itself no longer needs reversing, so
        # they must not block the document reversal.
        explicit_reversing_transactions = (
            all_txs.filter(type__in=self._reversable_transaction_types)
            .exclude(type__in=self._implicit_reversable_transaction_types)
            .filter(reversal_of__isnull=True, reversed_by__isnull=True)
        )

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
        """Reverse this record: guards, mirrors it and reverses its transactions.

        Validates that no explicit transactions or adjustments remain active,
        reverses the reversible ones, then clones the record linked via
        ``reversal_of``.
        """
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
            adjs = self.adjustments.filter(  # type: ignore
                deleted_at__isnull=True,
                reversed_by__isnull=True,
            ).all()
            if len(adjs) > 0:
                raise ValidationError(
                    _(
                        "You can't reverse this object as it has non-reversed adjustments. To continue, you should manually reverse all of them."
                    )
                )
        from apps.app_audit import context as provenance
        from apps.app_audit import reasons

        with provenance.derived(reasons.ROLE_REVERSAL, reasons.REASON_REVERSAL):
            for tx in all_txs.filter(
                type__in=self._reversable_transaction_types
            ).all():
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
