import typing
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import models
from django.db import transaction as db_transaction
from django.forms import ValidationError
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

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
        if not self.entity_type:
            raise ValidationError(_("Entity type is required."))

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
                raise ValidationError(_("System entity already exists."))
        if is_new and self.entity_type == EntityType.WORLD:
            if Entity.objects.filter(entity_type=EntityType.WORLD).exists():
                raise ValidationError(_("World entity already exists."))

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

    def assets_at(self, dt: typing.Any) -> Decimal:
        """
        Monetary assets of the fund as of dt:
        Cash Balance + Trade Receivables + Inventory + Loans Receivable + Worker Advances Receivable.
        """
        from apps.app_transaction.transaction_type import TransactionType

        # 1. Cash on hand
        cash = self.balance_at(dt)

        # 2. Trade Receivables (Sales issued but not yet collected)
        sales_issued = self._tx_sum(
            "incoming",
            [TransactionType.SALE_ISSUANCE, TransactionType.SALE_ADJUSTMENT_INCREASE],
            dt,
        )
        sales_issuance_decreased = self._tx_sum(
            "incoming", [TransactionType.SALE_ADJUSTMENT_DECREASE], dt
        )
        net_sales_issuance = sales_issued - sales_issuance_decreased

        # Collections move money from issuance to cash balance
        sales_collected = self._tx_sum(
            "incoming", [TransactionType.SALE_COLLECTION], dt
        )
        trade_receivable = net_sales_issuance - sales_collected

        # 3. Inventory Value (Purchases issued but not yet sold)
        # We treat the issuance of a purchase as "Stock In" and sale as "Stock Out"
        purchases_issued = self._tx_sum(
            "outgoing",
            [
                TransactionType.PURCHASE_ISSUANCE,
                TransactionType.PURCHASE_ADJUSTMENT_INCREASE,
            ],
            dt,
        )
        purchases_issuance_decreased = self._tx_sum(
            "outgoing", [TransactionType.PURCHASE_ADJUSTMENT_DECREASE], dt
        )
        net_purchases_issuance = purchases_issued - purchases_issuance_decreased

        # Inventory is what was bought minus what was sold (at cost/issuance value)
        # Note: In this system, we use the sale issuance amount as the inventory reduction.
        inventory_value = net_purchases_issuance - net_sales_issuance

        # 4. Loans we gave to others (Receivable)
        # Note: LOAN_ISSUANCE is a memo, LOAN_PAYMENT is the actual debt creation
        loaned = self._tx_sum("outgoing", [TransactionType.LOAN_PAYMENT], dt)
        recovered = self._tx_sum("incoming", [TransactionType.LOAN_REPAYMENT], dt)
        loans_receivable = loaned - recovered

        # 5. Advances we paid to workers (Receivable)
        advances_paid = self._tx_sum(
            "outgoing", [TransactionType.WORKER_ADVANCE_PAYMENT], dt
        )
        advances_recovered = self._tx_sum(
            "incoming", [TransactionType.WORKER_ADVANCE_REPAYMENT], dt
        )
        advances_receivable = advances_paid - advances_recovered

        return (
            cash
            + trade_receivable
            + inventory_value
            + loans_receivable
            + advances_receivable
        )

    def liabilities_at(self, dt: typing.Any) -> Decimal:
        """
        Monetary liabilities of the fund as of dt:
        Trade Payables + Loans Payable + Worker Advances Payable + Distributions Payable.
        """
        from apps.app_transaction.transaction_type import TransactionType

        # 1. Trade Payables (Purchases & Expenses)
        purchases_issued = self._tx_sum(
            "outgoing",
            [
                TransactionType.PURCHASE_ISSUANCE,
                TransactionType.PURCHASE_ADJUSTMENT_INCREASE,
                TransactionType.EXPENSE_ISSUANCE,
                TransactionType.EXPENSE_ADJUSTMENT_INCREASE,
            ],
            dt,
        )
        purchases_decreased = self._tx_sum(
            "outgoing",
            [
                TransactionType.PURCHASE_ADJUSTMENT_DECREASE,
                TransactionType.EXPENSE_ADJUSTMENT_DECREASE,
            ],
            dt,
        )
        purchases_paid = self._tx_sum(
            "outgoing",
            [TransactionType.PURCHASE_PAYMENT, TransactionType.EXPENSE_PAYMENT],
            dt,
        )
        trade_payable = purchases_issued - purchases_decreased - purchases_paid

        # 2. Loans we received from others (Payable)
        borrowed = self._tx_sum("incoming", [TransactionType.LOAN_PAYMENT], dt)
        repaid = self._tx_sum("outgoing", [TransactionType.LOAN_REPAYMENT], dt)
        loans_payable = borrowed - repaid

        # 3. Advances we received as worker (Payable)
        advances_received = self._tx_sum(
            "incoming", [TransactionType.WORKER_ADVANCE_PAYMENT], dt
        )
        advances_repaid = self._tx_sum(
            "outgoing", [TransactionType.WORKER_ADVANCE_REPAYMENT], dt
        )
        advances_payable = advances_received - advances_repaid

        # 4. Profit Distributions Payable
        dist_issued = self._tx_sum(
            "outgoing", [TransactionType.PROFIT_DISTRIBUTION_ISSUANCE], dt
        )
        dist_paid = self._tx_sum(
            "outgoing", [TransactionType.PROFIT_DISTRIBUTION_PAYMENT], dt
        )
        distributions_payable = dist_issued - dist_paid

        return trade_payable + loans_payable + advances_payable + distributions_payable

    @property
    def balance(self) -> Decimal:
        from datetime import date

        return self.balance_at(date.today())

    @property
    def assets(self) -> Decimal:
        from datetime import date

        return self.assets_at(date.today())

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
        if self.entity_type != EntityType.PROJECT:
            raise ValueError(_("profit_loss() is only defined for project funds."))

        from django.db.models import Case, F, Sum, When

        from apps.app_transaction.models import Transaction
        from apps.app_transaction.transaction_type import TransactionType

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

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        from apps.app_operation.models.period import FinancialPeriod

        with db_transaction.atomic():
            rv = super().save(*args, **kwargs)
            if is_new:
                if self.is_world or self.is_system:
                    ...
                else:
                    FinancialPeriod.objects.create(
                        entity=self,
                        start_date=self.created_at.date(),
                    )
            return rv

    # class Meta:
    #     verbose_name = _("fund")
    #     verbose_name_plural = _("funds")
