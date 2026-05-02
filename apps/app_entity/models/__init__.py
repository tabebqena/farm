import typing
from datetime import date as date_type
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import models
from django.db import transaction as db_transaction
from django.forms import ValidationError
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.app_base.debug import DebugContext
from apps.app_base.mixins import ImmutableMixin
from apps.app_base.models import BaseModel

if typing.TYPE_CHECKING:
    from apps.app_operation.models.period import FinancialPeriod

User = get_user_model()


class EntityType(models.TextChoices):
    PERSON = "person", _("Person")
    PROJECT = "project", _("Project")
    SYSTEM = "system", _("System")
    WORLD = "world", _("World")


class ContactInfo(ImmutableMixin, BaseModel):
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
        DebugContext.log(
            f"ContactInfo.save() ({action})",
            {
                "entity": str(self.entity),
                "contact_type": self.contact_type,
                "label": self.label,
            },
        )
        result = super().save(*args, **kwargs)
        DebugContext.audit(
            action=f"contact_info_{action}",
            entity_type="ContactInfo",
            entity_id=self.pk,
            details={"entity": str(self.entity), "type": self.contact_type},
            user="system",
        )
        return result

    def delete(self, *args, **kwargs):
        """Delete contact info with logging."""
        DebugContext.warn(
            "ContactInfo.delete()",
            {
                "entity": str(self.entity),
                "type": self.contact_type,
                "value": self.value[:50] if self.value else "",
            },
        )
        DebugContext.audit(
            action="contact_info_deleted",
            entity_type="ContactInfo",
            entity_id=self.pk,
            details={"entity": str(self.entity)},
            user="system",
        )
        return super().delete(*args, **kwargs)

    def __str__(self):
        return _("%(label)s: %(value)s") % {
            "label": self.get_label_display(),
            "value": self.value,
        }

    class Meta:
        verbose_name = _("contact info")
        verbose_name_plural = _("contact info")


class StakeholderRole(models.TextChoices):
    WORKER = "worker", _("Worker")
    CLIENT = "client", _("Client")
    VENDOR = "vendor", _("Vendor")
    SHAREHOLDER = "shareholder", _("Shareholder")


class Stakeholder(ImmutableMixin, BaseModel):
    _immutable_fields = {"parent": {}, "target": {}, "role": {}}

    parent = models.ForeignKey(
        "Entity",
        on_delete=models.CASCADE,
        related_name="stakeholders",
        verbose_name=_("parent"),
    )
    target = models.ForeignKey(
        "Entity",
        on_delete=models.CASCADE,
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
        DebugContext.log(
            f"Stakeholder.save() ({action})",
            {
                "parent": str(self.parent),
                "target": str(self.target),
                "role": self.role,
                "active": self.active,
            },
        )
        result = super().save(*args, **kwargs)
        DebugContext.audit(
            action=f"stakeholder_{action}",
            entity_type="Stakeholder",
            entity_id=self.pk,
            details={
                "parent": str(self.parent),
                "target": str(self.target),
                "role": self.role,
            },
            user="system",
        )
        return result

    def delete(self, *args, **kwargs):
        """Delete stakeholder with logging."""
        DebugContext.warn(
            "Stakeholder.delete()",
            {
                "parent": str(self.parent),
                "target": str(self.target),
                "role": self.role,
            },
        )
        DebugContext.audit(
            action="stakeholder_deleted",
            entity_type="Stakeholder",
            entity_id=self.pk,
            details={
                "parent": str(self.parent),
                "target": str(self.target),
                "role": self.role,
            },
            user="system",
        )
        return super().delete(*args, **kwargs)

    def clean(self) -> None:
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
    _immutable_fields = {
        "entity_type": {},
        "user": {},
    }

    entity_type = models.CharField(
        _("entity type"),
        max_length=10,
        choices=EntityType,
    )

    # Flat metadata
    name = models.CharField(_("name"), max_length=255, unique=True, blank=True)
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
        return self.entity_type == EntityType.SYSTEM

    @property
    def is_world(self) -> bool:
        return self.entity_type == EntityType.WORLD

    @property
    def is_virtual(self) -> bool:
        return self.entity_type in (EntityType.SYSTEM, EntityType.WORLD)

    @property
    def is_project(self) -> bool:
        return self.entity_type == EntityType.PROJECT

    @property
    def is_person(self) -> bool:
        return self.entity_type == EntityType.PERSON

    # TODO remove
    @property
    def owner(self):
        return self

    @property
    def type(self):
        return self.entity_type

    def get_display_name(self):
        return self.name

    def get_vendors(self):
        return self.stakeholders.filter(is_vendor=True, active=True)

    def get_clients(self):
        return self.stakeholders.filter(is_client=True, active=True)

    def get_workers(self):
        return self.stakeholders.filter(is_worker=True, active=True)

    def get_shareholders(self):
        return self.stakeholders.filter(is_shareholder=True, active=True)

    def get_absolute_url(self):
        return reverse("entity_detail", kwargs={"pk": self.pk})

    def __str__(self) -> str:
        return self.name or _("Entity #%(pk)s") % {"pk": self.pk}

    def clean(self) -> None:
        DebugContext.log(
            "Entity.clean()",
            {
                "is_new": self.pk is None,
                "pk": self.pk,
                "entity_type": self.entity_type,
                "name": self.name[:50] if self.name else "",
            },
        )

        if not self.entity_type:
            DebugContext.error("Entity type is required", data={"name": self.name})
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
                DebugContext.error("System entity already exists")
                raise ValidationError(_("System entity already exists."))
        if is_new and self.entity_type == EntityType.WORLD:
            if Entity.objects.filter(entity_type=EntityType.WORLD).exists():
                DebugContext.error("World entity already exists")
                raise ValidationError(_("World entity already exists."))

        DebugContext.success(
            "Entity validation passed",
            {
                "entity_type": self.entity_type,
                "name": self.name[:50] if self.name else "",
            },
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

    # TODO remove
    @property
    def fund(self):
        return self

    class Meta:
        verbose_name = _("entity")
        verbose_name_plural = _("entities")

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
        """Helper to sum transactions excluding those reversed before dt."""
        from django.db.models import Q, Sum

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

        return Transaction.objects.filter(**filters).filter(
            Q(reversed_by__isnull=True) | Q(reversed_by__date__date__gt=dt)
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    def payables_at(self, dt) -> Decimal:
        from apps.app_transaction.transaction_type import TransactionType as T

        increase_as_source = [
            T.PURCHASE_ISSUANCE,
            T.PURCHASE_ADJUSTMENT_INCREASE,
            T.SALE_ISSUANCE,
            T.SALE_ADJUSTMENT_INCREASE,
            T.EXPENSE_ISSUANCE,
            T.EXPENSE_ADJUSTMENT_INCREASE,
            T.PROFIT_DISTRIBUTION_ISSUANCE,
            T.PROJECT_REFUND_ISSUANCE,
        ]
        decrease_as_source = [
            T.PURCHASE_PAYMENT,
            T.SALE_COLLECTION,
            T.EXPENSE_PAYMENT,
            T.WORKER_ADVANCE_REPAYMENT,
            T.LOAN_REPAYMENT,
            T.PROFIT_DISTRIBUTION_PAYMENT,
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
            T.PROFIT_DISTRIBUTION_ISSUANCE,
            T.PROJECT_REFUND_ISSUANCE,
        ]
        decrease_as_target = [
            T.PURCHASE_PAYMENT,
            T.SALE_COLLECTION,
            T.EXPENSE_PAYMENT,
            T.WORKER_ADVANCE_REPAYMENT,
            T.LOAN_REPAYMENT,
            T.PROFIT_DISTRIBUTION_PAYMENT,
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
                               CAPITAL_GAIN_ISSUANCE, CORRECTION_CREDIT_ISSUANCE,
                               plus SALE/PURCHASE adjustment INCREASE; minus DECREASE.
        Costs   (source=fund): PURCHASE_ISSUANCE, EXPENSE_ISSUANCE, CAPITAL_LOSS_ISSUANCE,
                               CORRECTION_DEBIT_ISSUANCE, SALE_ISSUANCE (project as client),
                               plus PURCHASE/SALE/EXPENSE adjustment INCREASE; minus DECREASE.

        Reversal transactions are negated so that cross-period reversals land in the
        correct period with the correct sign.

        Raises ValueError if the fund's entity is not a project.
        """
        from apps.app_transaction.transaction_type import TransactionType

        if self.entity_type != EntityType.PROJECT:
            raise ValueError(_("profit_loss() is only defined for project funds."))

        from django.db.models import Case, F, Sum, When

        from apps.app_transaction.models import Transaction

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

        def _signed_sum(qs):
            """Sum amounts, negating reversal transactions for cross-period correctness."""
            return qs.aggregate(
                total=Sum(
                    Case(
                        When(reversal_of__isnull=False, then=-F("amount")),
                        default=F("amount"),
                    )
                )
            )["total"] or Decimal("0.00")

        # fund direction disambiguates edge cases naturally:
        # - target=fund + PURCHASE_ISSUANCE → project acting as vendor (income)
        # - source=fund + PURCHASE_ISSUANCE → project acting as buyer  (cost)
        # - target=fund + SALE_ISSUANCE     → project acting as seller (income)
        # - source=fund + SALE_ISSUANCE     → project acting as client (cost)
        income = _signed_sum(
            Transaction.objects.filter(
                target=fund,
                type__in=[
                    TransactionType.SALE_ISSUANCE,
                    TransactionType.CAPITAL_GAIN_ISSUANCE,
                    TransactionType.CORRECTION_CREDIT_ISSUANCE,
                    TransactionType.PURCHASE_ISSUANCE,  # project as vendor
                    TransactionType.SALE_ADJUSTMENT_INCREASE,
                    TransactionType.PURCHASE_ADJUSTMENT_INCREASE,  # project as vendor
                ],
                **tx_valid,
            )
        )
        income -= _signed_sum(
            Transaction.objects.filter(
                target=fund,
                type__in=[
                    TransactionType.SALE_ADJUSTMENT_DECREASE,
                    TransactionType.PURCHASE_ADJUSTMENT_DECREASE,  # project as vendor
                ],
                **tx_valid,
            )
        )

        costs = _signed_sum(
            Transaction.objects.filter(
                source=fund,
                type__in=[
                    TransactionType.PURCHASE_ISSUANCE,
                    TransactionType.EXPENSE_ISSUANCE,
                    TransactionType.CAPITAL_LOSS_ISSUANCE,
                    TransactionType.CORRECTION_DEBIT_ISSUANCE,
                    TransactionType.SALE_ISSUANCE,  # project as client
                    TransactionType.PURCHASE_ADJUSTMENT_INCREASE,
                    TransactionType.SALE_ADJUSTMENT_INCREASE,  # project as client
                    TransactionType.EXPENSE_ADJUSTMENT_INCREASE,
                ],
                **tx_valid,
            )
        )
        costs -= _signed_sum(
            Transaction.objects.filter(
                source=fund,
                type__in=[
                    TransactionType.PURCHASE_ADJUSTMENT_DECREASE,
                    TransactionType.SALE_ADJUSTMENT_DECREASE,  # project as client
                    TransactionType.EXPENSE_ADJUSTMENT_DECREASE,
                ],
                **tx_valid,
            )
        )

        return income - costs

    @property
    def balance(self) -> Decimal:
        from datetime import date

        return self.balance_at(date.today())

    @property
    def payables(self) -> Decimal:
        from datetime import date

        return self.payables_at(date.today())

    @property
    def receivables(self) -> Decimal:
        from datetime import date

        return self.receivables_at(date.today())

    @property
    def non_cash_assets(self) -> Decimal:
        from datetime import date

        return self.non_cash_assets_at(date.today())

    @property
    def assets(self) -> Decimal:
        from datetime import date

        return self.balance_at(date.today()) + self.non_cash_assets_at(date.today())

    @property
    def liabilities(self) -> Decimal:
        from datetime import date

        return self.liabilities_at(date.today())

    def can_pay(self, amount: Decimal) -> bool:
        if not self.active:
            return False
        if self.is_virtual:
            return True
        return self.balance >= amount

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        from apps.app_operation.models.period import FinancialPeriod

        with DebugContext.section(
            f"Entity.save() ({self.entity_type})",
            {
                "is_new": is_new,
                "pk": self.pk,
                "name": self.name[:50] if self.name else "",
                "entity_type": self.entity_type,
            },
        ):
            with db_transaction.atomic():
                rv = super().save(*args, **kwargs)
                if not (self.is_world or self.is_system):
                    open_period = self.financial_periods.filter(end_date__isnull=True).first()
                    if self.active and open_period is None:
                        start_date = self.created_at.date() if is_new else date_type.today()
                        FinancialPeriod.objects.create(entity=self, start_date=start_date)
                        DebugContext.log(
                            "Financial period created",
                            {
                                "entity_pk": self.pk,
                                "start_date": str(start_date),
                                "reason": "entity_activation" if not is_new else "entity_creation",
                            },
                        )
                    elif not self.active and open_period is not None:
                        from datetime import timedelta
                        end_date = date_type.today()
                        if end_date <= open_period.start_date:
                            end_date = open_period.start_date + timedelta(days=1)
                        open_period.end_date = end_date
                        open_period.save()
                        DebugContext.log(
                            "Financial period closed",
                            {
                                "entity_pk": self.pk,
                                "period_pk": open_period.pk,
                                "end_date": str(end_date),
                                "reason": "entity_deactivation",
                            },
                        )

                DebugContext.success("Entity saved", {"pk": self.pk})

                # Audit the operation
                action = "entity_created" if is_new else "entity_updated"
                DebugContext.audit(
                    action=action,
                    entity_type="Entity",
                    entity_id=self.pk,
                    details={
                        "name": self.name,
                        "entity_type": self.entity_type,
                        "is_internal": self.is_internal,
                    },
                    user="system",
                )

                return rv

    def delete(self, *args, **kwargs):
        """Delete entity with audit logging."""
        with DebugContext.section(
            "Entity.delete()",
            {
                "pk": self.pk,
                "name": self.name[:50] if self.name else "",
                "entity_type": self.entity_type,
            },
        ):
            DebugContext.warn(
                "Deleting entity",
                {
                    "pk": self.pk,
                    "name": self.name,
                    "entity_type": self.entity_type,
                },
            )

            DebugContext.audit(
                action="entity_deleted",
                entity_type="Entity",
                entity_id=self.pk,
                details={
                    "name": self.name,
                    "entity_type": self.entity_type,
                },
                user="system",
            )

            return super().delete(*args, **kwargs)

    # class Meta:
    #     verbose_name = _("fund")
    #     verbose_name_plural = _("funds")
