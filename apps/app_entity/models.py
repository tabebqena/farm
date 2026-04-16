import typing
from decimal import Decimal
from enum import Enum

from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.forms import ValidationError
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.app_base.mixins import ImmutableMixin
from apps.app_base.models import BaseModel

if typing.TYPE_CHECKING:
    from apps.app_operation.models.period import FinancialPeriod

User = get_user_model()


class Virtual:
    def __init__(self, name, type) -> None:
        self._name = name
        self.type = type

    @property
    def name(self):
        return self._name

    def get_display_name(self):
        return self.name


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


class Person(BaseModel):
    private_name = models.CharField(
        _("private name"), max_length=255, null=False, blank=False, unique=True
    )
    private_description = models.TextField(_("private description"), blank=True)

    def get_display_name(self):
        return self.private_name

    @property
    def name(self):
        return self.get_display_name()

    def __str__(self):
        return f"{self.name}"

    @classmethod
    def create(cls, private_name, private_description="", **kwargs):
        with transaction.atomic():
            try:
                p = Person(
                    private_name=private_name, private_description=private_description
                )
                p.save()
                e = Entity.create(owner=p, **kwargs)
                return p
            except:
                raise

    class Meta:
        verbose_name = _("person")
        verbose_name_plural = _("people")


class Project(ImmutableMixin, BaseModel):
    name = models.CharField(
        _("name"), max_length=255, null=False, blank=False, unique=True
    )
    description = models.CharField(
        _("description"), max_length=180, default="", null=True, blank=True
    )
    feasibility_study = models.FileField(_("feasibility study"), null=True, blank=True)
    start_date = models.DateTimeField(
        auto_now_add=True, verbose_name=_("the project start date")
    )
    end_date = models.DateTimeField(_("end date"), null=True, blank=True)

    def get_display_name(self):
        return self.name

    def __str__(self) -> str:
        return self.get_display_name()

    class Meta:
        verbose_name = _("project")
        verbose_name_plural = _("projects")


class Fund(ImmutableMixin, BaseModel):
    _immutable_fields = {"entity": {}}
    entity = models.OneToOneField(
        "Entity",
        on_delete=models.PROTECT,
        related_name="fund",
        null=False,
        blank=False,
        verbose_name=_("entity"),
    )
    active = models.BooleanField(_("active"), default=True)

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
        if self.entity.is_world or self.entity.is_system:
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
        if not self.entity.project:
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

    class Meta:
        verbose_name = _("fund")
        verbose_name_plural = _("funds")


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
        if not self.parent.project and not self.parent.person:
            raise ValidationError(
                _("The parent party should be a project or person entity.")
            )
        if not self.target.project and not self.target.person:
            raise ValidationError(
                _("The target party should be a project or person entity.")
            )
        if self.target.project and self.role in ("shareholder", "worker"):
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


ENTITY_TYPE_ENUM = Enum("Type", "PERSONAL PROJECT SYSTEM WORLD")


class Entity(ImmutableMixin, BaseModel):
    _immutable_fields = {
        "person": {},
        "project": {},
        "user": {},
        # "fund": {"ALLOW_SET": True},
        "is_system": {},
        "is_world": {},
    }

    person = models.OneToOneField(
        to="Person",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="entity",
        verbose_name=_("person"),
    )

    project = models.OneToOneField(
        to="Project",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="entity",
        verbose_name=_("project"),
    )

    user = models.OneToOneField(
        to=User,
        on_delete=models.PROTECT,
        related_name="entity",
        null=True,
        blank=True,
        verbose_name=_("user"),
    )

    is_internal = models.BooleanField(_("is internal"), default=False)

    is_system = models.BooleanField(_("is system"), default=False)
    is_world = models.BooleanField(_("is world"), default=False)

    is_vendor = models.BooleanField(_("is vendor"), default=False)
    is_client = models.BooleanField(_("is client"), default=False)
    is_worker = models.BooleanField(_("is worker"), default=False)
    is_shareholder = models.BooleanField(_("is shareholder"), default=False)

    active = models.BooleanField(_("active"), default=True)

    @property
    def owner(self):
        a = self.project or self.person
        if a:
            return a
        if self.is_system:
            return Virtual(_("System"), "SYSTEM")
        if self.is_world:
            return Virtual(_("World"), "WORLD")

    @property
    def type(self):
        if self.project:
            return ENTITY_TYPE_ENUM.PROJECT
        elif self.person:
            return ENTITY_TYPE_ENUM.PERSONAL
        elif self.is_system:
            return ENTITY_TYPE_ENUM.SYSTEM
        elif self.is_world:
            return ENTITY_TYPE_ENUM.WORLD

    def get_vendors(self):
        return self.stakeholders.filter(is_vendor=True, active=True)

    def get_clients(self):
        return self.stakeholders.filter(is_client=True, active=True)

    def get_workers(self):
        return self.stakeholders.filter(is_worker=True, active=True)

    def get_shareholders(self):
        return self.stakeholders.filter(is_shareholder=True, active=True)

    def get_display_name(self):
        return self.owner.get_display_name()  # type: ignore

    @property
    def name(self):
        return self.get_display_name()

    @property
    def is_virtual(self):
        return self.is_world or self.is_system

    def get_absolute_url(self):
        return reverse("entity_detail", kwargs={"pk": self.pk})

    def __str__(self) -> str:
        return _("Entity %(owner)s") % {"owner": self.owner}

    def clean(self) -> None:
        # 1. Count the types of identities
        # bool() on a model instance checks if it has a PK/is not None
        identity_sources = [
            bool(self.person),
            bool(self.project),
            self.is_system,
            self.is_world,
        ]
        active_count = sum(1 for i in identity_sources if i)

        if active_count == 0:
            raise ValueError(
                _(
                    "Entity must have exactly one identity (Person, Project, System, or World). This entity has %(count)s identities: %(sources)s"
                )
                % {"count": active_count, "sources": identity_sources}
            )
        if active_count > 1:
            raise ValidationError(
                _("Entity cannot represent multiple identities simultaneously.")
            )

        if self.is_system:
            self.is_internal = True
        elif self.is_world:
            self.is_internal = False

        if self.is_virtual:
            self.is_vendor = False
            self.is_worker = False
            self.is_client = False
            self.is_shareholder = False

        is_new = self.pk is None
        if is_new and self.is_system:
            # Disallow duplicate
            exists = Entity.objects.filter(is_system=True).exists()
            if exists:
                raise ValidationError(_("System entity already exists."))
        if is_new and self.is_world:
            # Disallow duplicate
            exists = Entity.objects.filter(is_world=True).exists()
            if exists:
                raise ValidationError(_("World entity already exists."))

        if getattr(self, "fund", None) is None:
            self.active = False

        return super().clean()

    def get_fund(self):
        return Fund.objects.get_or_create(entity=self)

    @classmethod
    def create(
        cls,
        owner=None,
        fund=None,
        auth_user=None,
        is_system=False,
        is_world=False,
        is_vendor=False,
        is_client=False,
        is_worker=False,
        is_shareholder=False,
        is_internal=False,
        active=True,
        fund_active=True,
    ):
        with transaction.atomic():
            e = Entity()
            if isinstance(owner, Person):
                e.person = owner
            elif isinstance(owner, Project):
                e.project = owner
            e.user = auth_user
            e.is_system = is_system
            e.is_world = is_world
            e.is_client = is_client
            e.is_vendor = is_vendor
            e.is_worker = is_worker
            e.is_shareholder = is_shareholder
            e.is_internal = is_internal
            e.active = False

            e.save()
            if fund is None:
                fund = Fund.objects.create(entity=e, active=fund_active)
            e.active = active
            e.save()
            return e

    class Meta:
        verbose_name = _("entity")
        verbose_name_plural = _("entities")
