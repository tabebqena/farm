"""Entity domain models.

Defines :class:`Entity` (persons, projects, and system / virtual / world
entities), :class:`ContactInfo`, :class:`Stakeholder` and the
:class:`EntityType` / :class:`StakeholderRole` choice sets, together with the
balance, payables, receivables and profit/loss computations that derive from the
entity's financial transactions.
"""

import typing
from datetime import date as date_type
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import models
from django.db import transaction as db_transaction
from django.forms import ValidationError
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.app_base.logging_utils import audit_logger, logger
from apps.app_base.mixins import ImmutableMixin
from apps.app_base.models import BaseModel

if typing.TYPE_CHECKING:
    from apps.app_operation.models.period import FinancialPeriod

User = get_user_model()


def _profit_loss_income_types():
    """Income transaction-type lists driving ``Entity.profit_loss()``.

    Returns ``(increase_types, decrease_types)``. Imported lazily to avoid a
    circular import (``transaction_type`` builds an operation map at import).
    See the method docstring for the project-as-vendor direction semantics.
    """
    from apps.app_transaction.transaction_type import TransactionType

    return (
        [
            TransactionType.SALE_ISSUANCE,
            TransactionType.CORRECTION_CREDIT_ISSUANCE,
            TransactionType.PURCHASE_ISSUANCE,  # project as vendor
            TransactionType.SALE_ADJUSTMENT_INCREASE,
            TransactionType.PURCHASE_ADJUSTMENT_INCREASE,  # project as vendor
        ],
        [
            TransactionType.SALE_ADJUSTMENT_DECREASE,
            TransactionType.PURCHASE_ADJUSTMENT_DECREASE,  # project as vendor
        ],
    )


def _profit_loss_cost_types():
    """Cost transaction-type lists driving ``Entity.profit_loss()``.

    Returns ``(increase_types, decrease_types)``. Imported lazily to avoid a
    circular import (``transaction_type`` builds an operation map at import).
    See the method docstring for the project-as-client direction semantics.
    """
    from apps.app_transaction.transaction_type import TransactionType

    return (
        [
            TransactionType.PURCHASE_ISSUANCE,
            TransactionType.EXPENSE_ISSUANCE,
            TransactionType.CORRECTION_DEBIT_ISSUANCE,
            TransactionType.SALE_ISSUANCE,  # project as client
            TransactionType.PURCHASE_ADJUSTMENT_INCREASE,
            TransactionType.SALE_ADJUSTMENT_INCREASE,  # project as client
            TransactionType.EXPENSE_ADJUSTMENT_INCREASE,
        ],
        [
            TransactionType.PURCHASE_ADJUSTMENT_DECREASE,
            TransactionType.SALE_ADJUSTMENT_DECREASE,  # project as client
            TransactionType.EXPENSE_ADJUSTMENT_DECREASE,
        ],
    )


def _fund_transaction_sum(fund, *, direction, types, tx_valid):
    """Signed sum of transactions on the given side of the *fund*.

    ``direction`` is ``"target"`` (the fund receives → income) or ``"source"``
    (the fund pays → cost). Reversal transactions are negated so cross-period
    reversals land in the correct period with the correct sign.
    """
    from django.db.models import Case, F, Sum, When

    from apps.app_transaction.models import Transaction

    return (
        Transaction.objects.filter(
            **{direction: fund},
            type__in=types,
            **tx_valid,
        ).aggregate(
            total=Sum(
                Case(
                    When(reversal_of__isnull=False, then=-F("amount")),
                    default=F("amount"),
                )
            )
        )["total"]
        or Decimal("0.00")
    )


class EntityType(models.TextChoices):
    """The kind of an :class:`Entity`: person, project, system or world."""

    PERSON = "person", _("Person")
    PROJECT = "project", _("Project")
    SYSTEM = "system", _("System")
    WORLD = "world", _("World")


class ContactInfo(ImmutableMixin, BaseModel):
    """Contact details (phone / email / address / website) attached to an entity.

    Values are immutable once saved; a single record per entity may be flagged
    as the primary contact.
    """

    TYPES = [
        ("phone", _("Phone")),
        ("email", _("Email")),
        ("address", _("Address")),
        ("website", _("Website")),
    ]

    LabelTypes = [
        ("work", _("Work")),
        ("personal", _("Personal")),
        ("home", _("Home")),
    ]

    entity = models.ForeignKey(
        "Entity",
        on_delete=models.PROTECT,
        related_name="contacts",
        verbose_name=_("entity"),
    )
    contact_type = models.CharField(_("contact type"), max_length=20, choices=TYPES)
    value = models.CharField(_("value"), max_length=255)
    label = models.CharField(_("label"), max_length=50, choices=LabelTypes)
    is_primary = models.BooleanField(_("is primary"), default=False)

    def save(self, *args, **kwargs):
        """Save contact info with logging."""
        is_new = self.pk is None
        action = "created" if is_new else "updated"
        logger.debug(
            f"ContactInfo.save() ({action}) | entity={self.entity} | "
            f"contact_type={self.contact_type} | label={self.label}"
        )
        result = super().save(*args, **kwargs)
        audit_logger.info(
            f"contact_info_{action} | ContactInfo:{self.pk} | user=system | "
            f"entity={self.entity} | type={self.contact_type}"
        )
        return result

    def __str__(self):
        return _("%(label)s: %(value)s") % {
            "label": self.get_label_display(),
            "value": self.value,
        }

    class Meta:
        verbose_name = _("contact info")
        verbose_name_plural = _("contact info")


class StakeholderRole(models.TextChoices):
    """The role a person holds in a project: worker, client, vendor or shareholder."""

    WORKER = "worker", _("Worker")
    CLIENT = "client", _("Client")
    VENDOR = "vendor", _("Vendor")
    SHAREHOLDER = "shareholder", _("Shareholder")


class Stakeholder(ImmutableMixin, BaseModel):
    """Links a person to a project under a fixed role.

    ``parent`` (a project or person) owns the relationship and ``target`` is the
    person acting in ``role`` — worker, vendor, client or shareholder. Both
    parties must be person / project entities and the role/parties are immutable.
    """

    _immutable_fields = {"parent": {}, "target": {}, "role": {}}

    # PROTECT, not CASCADE: BaseModel.delete() soft-deletes only and never
    # cascades, so a stakeholder link is a protected dependent of both parties —
    # an entity can't be deleted while it still has stakeholders/memberships.
    parent = models.ForeignKey(
        "Entity",
        on_delete=models.PROTECT,
        related_name="stakeholders",
        verbose_name=_("parent"),
    )
    target = models.ForeignKey(
        "Entity",
        on_delete=models.PROTECT,
        related_name="memberships",
        verbose_name=_("target"),
    )
    role = models.CharField(_("role"), max_length=30, choices=StakeholderRole)
    notes = models.TextField(_("notes"), blank=True)
    active = models.BooleanField(_("active"), default=True)

    def save(self, *args, **kwargs):
        """Save stakeholder with logging."""
        is_new = self.pk is None
        action = "created" if is_new else "updated"
        logger.debug(
            f"Stakeholder.save() ({action}) | parent={self.parent} | target={self.target} | "
            f"role={self.role} | active={self.active}"
        )
        result = super().save(*args, **kwargs)
        audit_logger.info(
            f"stakeholder_{action} | Stakeholder:{self.pk} | user=system | "
            f"parent={self.parent} | target={self.target} | role={self.role}"
        )
        return result

    def clean(self) -> None:
        """Validate the parent/target entity types and role compatibility."""
        allowed = {EntityType.PERSON, EntityType.PROJECT}
        if self.parent.entity_type not in allowed:
            raise ValidationError(
                _("The parent party should be a project or person entity.")
            )
        if self.target.entity_type not in allowed:
            raise ValidationError(
                _("The target party should be a project or person entity.")
            )
        if self.target.entity_type == EntityType.PROJECT and self.role in (
            "shareholder",
            "worker",
        ):
            raise ValidationError(
                _(
                    "The target party (project) can't be assigned as a worker or a shareholder."
                )
            )
        return super().clean()

    def __str__(self):
        return _("%(target)s as %(role)s in %(parent)s") % {
            "target": self.target,
            "role": self.get_role_display(),
            "parent": self.parent,
        }

    class Meta:
        verbose_name = _("stakeholder")
        verbose_name_plural = _("stakeholders")


class Entity(ImmutableMixin, BaseModel):
    """A participant in the farm's financial world.

    Persons, projects and the system / world entities all live on this table,
    and each entity doubles as a fund whose balance, payables and receivables
    are derived from its transactions. ``entity_type`` and the role flags are
    immutable after creation.
    """

    _immutable_fields = {
        "entity_type": {},
        "user": {},
    }

    # Reverse relations whose live rows are AUTO soft-deleted when this entity
    # is deleted (instead of blocking the deletion guard). These are owned
    # light rows — contact details, stakeholder/membership links, category
    # relations, and the auto-created financial periods. Financial history
    # (products, operations, transactions) is NOT listed and therefore still
    # blocks deletion until handled first.
    _delete_auto_relations = (
        "contacts",
        "stakeholders",
        "memberships",
        "financial_categories_entities_relations",
        "financial_periods",
    )

    entity_type = models.CharField(
        _("entity type"),
        max_length=10,
        choices=EntityType,
    )

    # Flat metadata
    name = models.CharField(_("name"), max_length=255, blank=True)
    description = models.TextField(_("description"), blank=True)

    # Project-only metadata (null for non-projects)
    feasibility_study = models.FileField(_("feasibility study"), null=True, blank=True)
    start_date = models.DateTimeField(_("start date"), null=True, blank=True)
    end_date = models.DateTimeField(_("end date"), null=True, blank=True)

    user = models.OneToOneField(
        to=User,
        on_delete=models.PROTECT,
        related_name="entity",
        null=True,
        blank=True,
        verbose_name=_("user"),
    )

    is_internal = models.BooleanField(_("is internal"), default=False)
    is_vendor = models.BooleanField(_("is vendor"), default=False)
    is_client = models.BooleanField(_("is client"), default=False)
    is_worker = models.BooleanField(_("is worker"), default=False)
    is_shareholder = models.BooleanField(_("is shareholder"), default=False)
    active = models.BooleanField(_("active"), default=True)

    # ------------------------------------------------------------------ #
    # Derived properties                                                   #
    # ------------------------------------------------------------------ #

    @property
    def is_system(self) -> bool:
        """True for the singleton System entity."""
        return self.entity_type == EntityType.SYSTEM

    @property
    def is_world(self) -> bool:
        """True for the singleton World entity."""
        return self.entity_type == EntityType.WORLD

    @property
    def is_virtual(self) -> bool:
        """True for the virtual System or World entities."""
        return self.entity_type in (EntityType.SYSTEM, EntityType.WORLD)

    @property
    def is_project(self) -> bool:
        """True for Project entities."""
        return self.entity_type == EntityType.PROJECT

    @property
    def is_person(self) -> bool:
        """True for Person entities."""
        return self.entity_type == EntityType.PERSON

    def get_display_name(self):
        """Human-readable name for templates/links."""
        return self.name

    def get_absolute_url(self):
        """URL of the entity's detail page."""
        return reverse("entity_detail", kwargs={"pk": self.pk})

    def __str__(self) -> str:
        return self.name or _("Entity #%(pk)s") % {"pk": self.pk}

    def clean(self) -> None:
        """Enforce type rules and the System/World singletons on create."""
        logger.debug(
            f"Entity.clean() | is_new={self.pk is None} | pk={self.pk} | "
            f"entity_type={self.entity_type} | name={self.name[:50] if self.name else ''}"
        )

        if not self.entity_type:
            logger.error(f"Entity type is required | name={self.name}")
            raise ValidationError(_("Entity type is required. --"))

        if self.entity_type == EntityType.SYSTEM:
            self.is_internal = True
        elif self.entity_type == EntityType.WORLD:
            self.is_internal = False

        if self.is_virtual:
            self.is_vendor = False
            self.is_worker = False
            self.is_client = False
            self.is_shareholder = False

        is_new = self.pk is None
        if is_new and self.entity_type == EntityType.SYSTEM:
            if Entity.objects.filter(entity_type=EntityType.SYSTEM).exists():
                logger.error("System entity already exists")
                raise ValidationError(_("System entity already exists."))
        if is_new and self.entity_type == EntityType.WORLD:
            if Entity.objects.filter(entity_type=EntityType.WORLD).exists():
                logger.error("World entity already exists")
                raise ValidationError(_("World entity already exists."))

        logger.debug(
            f"Entity validation passed | entity_type={self.entity_type} | "
            f"name={self.name[:50] if self.name else ''}"
        )
        return super().clean()

    @classmethod
    def create(
        cls,
        entity_type: EntityType,
        name="",
        description="",
        auth_user=None,
        # role flags
        is_vendor=False,
        is_client=False,
        is_worker=False,
        is_shareholder=False,
        is_internal=False,
        active=True,
        # project-specific
        feasibility_study=None,
        start_date=None,
        end_date=None,
    ):
        """Create an entity (person/project/system/world) with proper defaults."""
        with db_transaction.atomic():
            # Resolve entity_type from legacy kwargs or owner type

            e = Entity()
            e.entity_type = entity_type
            # Canonical names for virtual singletons
            if entity_type == EntityType.SYSTEM:
                name = "System"
            elif entity_type == EntityType.WORLD:
                name = "World"

            e.name = name
            e.description = description
            e.user = auth_user
            e.is_client = is_client
            e.is_vendor = is_vendor
            e.is_worker = is_worker
            e.is_shareholder = is_shareholder
            e.is_internal = is_internal
            e.active = False

            if feasibility_study is not None:
                e.feasibility_study = feasibility_study
            if start_date is not None:
                e.start_date = start_date
            if end_date is not None:
                e.end_date = end_date

            e.save()
            e.active = active
            e.save()
            return e

    class Meta:
        verbose_name = _("entity")
        verbose_name_plural = _("entities")
        # Uniqueness is scoped to live rows only, so a soft-deleted entity no
        # longer keeps its name "taken" forever (the old ``unique=True``
        # applied to tombstones as well). The form-level live-only duplicate
        # check (see PersonForm/ProjectForm.clean_name) stays consistent.
        constraints = [
            models.UniqueConstraint(
                fields=["name"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_entity_name_live",
            )
        ]

    # TODO consider revising the transaction type BIRTH, DEATH, CONSUMPTION
    def balance_at(self, dt) -> Decimal:
        """
        Fund balance as of dt (a date or datetime).
        Includes reversed and reversal transactions so that cross-period
        reversals land in the correct period with the correct sign.
        """
        from apps.app_transaction.transaction_type import TransactionType

        types = TransactionType.payment_types()
        return self._tx_sum("incoming", types, dt) - self._tx_sum("outgoing", types, dt)

    def _tx_sum(
        self, direction: str, types: typing.Iterable[str], dt: typing.Any
    ) -> Decimal:
        """Helper to sum transactions of specific types in a given direction."""
        from django.db.models import Sum

        from apps.app_transaction.models import Transaction

        filters = dict(
            deleted_at__isnull=True,
            type__in=types,
            date__date__lte=dt,
        )
        if direction == "incoming":
            filters["target"] = self  # type: ignore
        else:
            filters["source"] = self  # type: ignore

        return Transaction.objects.filter(**filters).aggregate(total=Sum("amount"))[
            "total"
        ] or Decimal("0.00")

    def _tx_sum_excluding_reversed(
        self, direction: str, types: typing.Iterable[str], dt: typing.Any
    ) -> Decimal:
        """Helper to sum transactions excluding those reversed before dt.

        Also excludes reversal (mirror) transactions: they are not independent
        obligations — they only undo an original that is already excluded here —
        and their swapped source/target role would otherwise be miscounted in
        the payables/receivables buckets.
        """
        from django.db.models import Q, Sum

        from apps.app_transaction.models import Transaction

        filters = dict(
            deleted_at__isnull=True,
            type__in=types,
            date__date__lte=dt,
            reversal_of__isnull=True,
        )
        if direction == "incoming":
            filters["target"] = self  # type: ignore
        else:
            filters["source"] = self  # type: ignore

        return Transaction.objects.filter(**filters).filter(
            Q(reversed_by__isnull=True) | Q(reversed_by__date__date__gt=dt)
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    def payables_at(self, dt) -> Decimal:
        """Amount this entity owes as of *dt* (net, reversal-aware)."""
        from apps.app_transaction.transaction_type import TransactionType as T

        increase_as_source = [
            T.PURCHASE_ISSUANCE,
            T.PURCHASE_ADJUSTMENT_INCREASE,
            T.SALE_ISSUANCE,
            T.SALE_ADJUSTMENT_INCREASE,
            T.EXPENSE_ISSUANCE,
            T.EXPENSE_ADJUSTMENT_INCREASE,
            T.PROJECT_REFUND_ISSUANCE,
        ]
        decrease_as_source = [
            T.PURCHASE_PAYMENT,
            T.SALE_COLLECTION,
            T.EXPENSE_PAYMENT,
            T.WORKER_ADVANCE_REPAYMENT,
            T.LOAN_REPAYMENT,
            T.PROJECT_REFUND_PAYMENT,
        ]
        increase_as_target = [T.WORKER_ADVANCE_PAYMENT, T.LOAN_PAYMENT]
        decrease_as_target = [
            T.PURCHASE_ADJUSTMENT_DECREASE,
            T.SALE_ADJUSTMENT_DECREASE,
            T.EXPENSE_ADJUSTMENT_DECREASE,
        ]
        return (
            self._tx_sum_excluding_reversed("outgoing", increase_as_source, dt)
            - self._tx_sum_excluding_reversed("outgoing", decrease_as_source, dt)
            + self._tx_sum_excluding_reversed("incoming", increase_as_target, dt)
            - self._tx_sum_excluding_reversed("incoming", decrease_as_target, dt)
        )

    def receivables_at(self, dt) -> Decimal:
        """Amount owed to this entity as of *dt* (net, reversal-aware)."""
        from apps.app_transaction.transaction_type import TransactionType as T

        increase_as_source = [T.WORKER_ADVANCE_PAYMENT, T.LOAN_PAYMENT]
        decrease_as_source = [
            T.PURCHASE_ADJUSTMENT_DECREASE,
            T.SALE_ADJUSTMENT_DECREASE,
            T.EXPENSE_ADJUSTMENT_DECREASE,
        ]
        increase_as_target = [
            T.PURCHASE_ISSUANCE,
            T.PURCHASE_ADJUSTMENT_INCREASE,
            T.SALE_ISSUANCE,
            T.SALE_ADJUSTMENT_INCREASE,
            T.EXPENSE_ISSUANCE,
            T.EXPENSE_ADJUSTMENT_INCREASE,
            T.PROJECT_REFUND_ISSUANCE,
        ]
        decrease_as_target = [
            T.PURCHASE_PAYMENT,
            T.SALE_COLLECTION,
            T.EXPENSE_PAYMENT,
            T.WORKER_ADVANCE_REPAYMENT,
            T.LOAN_REPAYMENT,
            T.PROJECT_REFUND_PAYMENT,
        ]
        return (
            self._tx_sum_excluding_reversed("outgoing", increase_as_source, dt)
            - self._tx_sum_excluding_reversed("outgoing", decrease_as_source, dt)
            + self._tx_sum_excluding_reversed("incoming", increase_as_target, dt)
            - self._tx_sum_excluding_reversed("incoming", decrease_as_target, dt)
        )

    def profit_loss(self, period: typing.Optional["FinancialPeriod"] = None) -> Decimal:
        """
        P&L for a project fund, driven entirely by issuance/adjustment transactions.

        Income  (target=fund): SALE_ISSUANCE, PURCHASE_ISSUANCE (project as vendor),
                               CORRECTION_CREDIT_ISSUANCE,
                               plus SALE/PURCHASE adjustment INCREASE; minus DECREASE.
        Costs   (source=fund): PURCHASE_ISSUANCE, EXPENSE_ISSUANCE,
                               CORRECTION_DEBIT_ISSUANCE, SALE_ISSUANCE (project as client),
                               plus PURCHASE/SALE/EXPENSE adjustment INCREASE; minus DECREASE.

        Capital Gain / Loss and Consumption are NOT accounting transactions anymore:
        they are stock events whose P&L effect flows through inventory value
        (`stock.inventory_value()` / `FinancialPeriod.end_assets`) instead of P&L.

        Reversal transactions are negated so that cross-period reversals land in the
        correct period with the correct sign.

        Raises ValueError if the fund's entity is not a project.
        """
        if self.entity_type != EntityType.PROJECT:
            raise ValueError(_("profit_loss() is only defined for project funds."))

        fund = self
        # Include both originals and their reversals so that cross-period reversals
        # are counted with the correct sign in each period (reversals are negated below).
        tx_valid: typing.Dict[str, typing.Any] = dict(deleted_at__isnull=True)
        if period:
            # Use __date to compare the DateTimeField as a date, avoiding
            # midnight-coercion issues when comparing against DateField values.
            # [start_date, end_date) — end_date is excluded, so __lt not __lte.
            tx_valid["date__date__gte"] = period.start_date
            if period.end_date is not None:
                tx_valid["date__date__lt"] = period.end_date

        # fund direction disambiguates edge cases naturally:
        # - target=fund + PURCHASE_ISSUANCE → project acting as vendor (income)
        # - source=fund + PURCHASE_ISSUANCE → project acting as buyer  (cost)
        # - target=fund + SALE_ISSUANCE     → project acting as seller (income)
        # - source=fund + SALE_ISSUANCE     → project acting as client (cost)
        income_types, income_decrease_types = _profit_loss_income_types()
        cost_types, cost_decrease_types = _profit_loss_cost_types()

        income = _fund_transaction_sum(
            fund,
            direction="target",
            types=income_types,
            tx_valid=tx_valid,
        )
        income -= _fund_transaction_sum(
            fund,
            direction="target",
            types=income_decrease_types,
            tx_valid=tx_valid,
        )

        costs = _fund_transaction_sum(
            fund,
            direction="source",
            types=cost_types,
            tx_valid=tx_valid,
        )
        costs -= _fund_transaction_sum(
            fund,
            direction="source",
            types=cost_decrease_types,
            tx_valid=tx_valid,
        )

        return income - costs

    @property
    def balance(self) -> Decimal:
        """Current fund balance (as of today)."""
        from datetime import date

        return self.balance_at(date.today())

    @property
    def payables(self) -> Decimal:
        """Current payables (as of today)."""
        from datetime import date

        return self.payables_at(date.today())

    @property
    def receivables(self) -> Decimal:
        """Current receivables (as of today)."""
        from datetime import date

        return self.receivables_at(date.today())

    def can_pay(self, amount: Decimal) -> bool:
        """True if the entity is active and (for real internal funds) can cover *amount*."""
        if not self.active:
            return False
        # Only real (non-virtual) internal funds are balance-checked. External
        # funds (clients/vendors) and virtual funds (system/world) have no
        # enforceable balance, so they are always allowed to pay.
        if self.is_virtual or not self.is_internal:
            return True
        return self.balance >= amount

    def save(self, *args, **kwargs):
        """Persist the entity and keep its open financial period in sync.

        On activation/creation an open period is auto-created; on deactivation
        the open period is closed.
        """
        is_new = self.pk is None
        from apps.app_operation.models.period import FinancialPeriod
        from apps.app_audit import context as provenance
        from apps.app_audit import reasons

        with db_transaction.atomic():
            rv = super().save(*args, **kwargs)
            if not (self.is_world or self.is_system):
                open_period = self.financial_periods.filter(end_date__isnull=True).first()
                if self.active and open_period is None:
                    start_date = self.created_at.date() if is_new else date_type.today()
                    with provenance.derived(
                        reasons.ROLE_PERIOD, reasons.REASON_PERIOD_CREATED
                    ):
                        FinancialPeriod.objects.create(
                            entity=self, start_date=start_date
                        )
                    logger.debug(
                        f"Financial period created | entity_pk={self.pk} | "
                        f"start_date={start_date} | "
                        f"reason={'entity_activation' if not is_new else 'entity_creation'}"
                    )
                elif not self.active and open_period is not None:
                    from datetime import timedelta
                    end_date = date_type.today()
                    if end_date <= open_period.start_date:
                        end_date = open_period.start_date + timedelta(days=1)
                    open_period.end_date = end_date
                    with provenance.derived(
                        reasons.ROLE_PERIOD, reasons.REASON_PERIOD_CLOSED
                    ):
                        open_period.save()
                    logger.debug(
                        f"Financial period closed | entity_pk={self.pk} | "
                        f"period_pk={open_period.pk} | end_date={end_date} | "
                        f"reason=entity_deactivation"
                    )

            logger.debug(f"Entity saved | pk={self.pk}")

            # Audit the operation
            action = "entity_created" if is_new else "entity_updated"
            audit_logger.info(
                f"{action} | Entity:{self.pk} | user=system | "
                f"name={self.name} | entity_type={self.entity_type} | "
                f"is_internal={self.is_internal}"
            )

            return rv

    def delete(self, *args, **kwargs):
        """Delete entity with audit logging."""
        logger.warning(
            f"Deleting entity | pk={self.pk} | name={self.name} | "
            f"entity_type={self.entity_type}"
        )

        audit_logger.info(
            f"entity_deleted | Entity:{self.pk} | user=system | "
            f"name={self.name} | entity_type={self.entity_type}"
        )

        return super().delete(*args, **kwargs)
