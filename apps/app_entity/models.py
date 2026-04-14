from decimal import Decimal
from enum import Enum

from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.forms import ValidationError
from django.urls import reverse

from apps.app_base.mixins import ImmutableMixin
from apps.app_base.models import BaseModel

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
        ("phone", "Phone"),
        ("email", "Email"),
        ("address", "Address"),
        ("website", "Website"),
    ]

    LabelTypes = [
        ("work", "Work"),
        ("personal", "Personal"),
        ("home", "Home"),
    ]

    entity = models.ForeignKey(
        "Entity", on_delete=models.PROTECT, related_name="contacts"
    )
    contact_type = models.CharField(max_length=20, choices=TYPES)
    value = models.CharField(max_length=255)
    label = models.CharField(max_length=50, choices=LabelTypes)
    is_primary = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.label}: {self.value}"


class Person(BaseModel):
    private_name = models.CharField(
        max_length=255, null=False, blank=False, unique=True
    )
    private_description = models.TextField(blank=True)

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


class Project(ImmutableMixin, BaseModel):
    name = models.CharField(max_length=255, null=False, blank=False, unique=True)
    description = models.CharField(max_length=180, default="", null=True, blank=True)
    feasibility_study = models.FileField(null=True, blank=True)
    start_date = models.DateTimeField(
        auto_now_add=True, verbose_name="the project start date"
    )
    end_date = models.DateTimeField(null=True, blank=True)

    def get_display_name(self):
        return self.name

    def __str__(self) -> str:
        return self.get_display_name()


class Fund(ImmutableMixin, BaseModel):
    _immutable_fields = {"entity": {}}
    entity = models.OneToOneField(
        "Entity", on_delete=models.PROTECT, related_name="fund", null=False, blank=False
    )
    active = models.BooleanField(default=True)

    @property
    def balance(self):
        from django.db.models import Sum

        from apps.app_transaction.models import Transaction
        from apps.app_transaction.transaction_type import TransactionType

        valid = dict(
            deleted_at__isnull=True,
            reversal_of__isnull=True,
            reversed_by__isnull=True,
            type__in=TransactionType.payment_types(),
        )
        incoming = Transaction.objects.filter(target=self, **valid).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")
        outgoing = Transaction.objects.filter(source=self, **valid).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")
        return incoming - outgoing

    def can_pay(self, amount: Decimal) -> bool:
        if not self.active:
            return False
        if self.entity.is_world or self.entity.is_system:
            return True
        return self.balance >= amount

    def profit_loss(self) -> Decimal:
        """
        P&L for a project fund, driven by issuance transactions so that
        adjustments (discounts, returns, surcharges) are included automatically.

        Income: issuance transactions where this fund is the target
                (Sale, Capital Gain, Correction Credit, and Purchase where project is vendor).
        Costs:  issuance transactions where this fund is the source
                (Purchase, Expense, Capital Loss, Correction Debit, and Sale where project is client).
        Adjustments: net of INCREASE minus DECREASE per Adjustment.effect,
                     resolved through the transaction records created at adjustment time.

        Raises ValueError if the fund's entity is not a project.
        """
        if not self.entity.project:
            raise ValueError("profit_loss() is only defined for project funds.")

        from django.contrib.contenttypes.models import ContentType
        from django.db.models import Sum

        from apps.app_adjustment.models import Adjustment, AdjustmentEffect
        from apps.app_operation.models.operation_type import OperationType
        from apps.app_transaction.models import Transaction
        from apps.app_transaction.transaction_type import TransactionType

        fund = self.entity.fund

        tx_valid = dict(
            deleted_at__isnull=True,
            reversal_of__isnull=True,
            reversed_by__isnull=True,
        )

        # fund direction disambiguates the edge cases naturally:
        # - target=fund + PURCHASE_ISSUANCE → project acting as vendor (income)
        # - source=fund + PURCHASE_ISSUANCE → project acting as buyer  (cost)
        # - target=fund + SALE_ISSUANCE     → project acting as seller (income, but filtered via source below)
        # - source=fund + SALE_ISSUANCE     → project acting as client (cost)
        income = Transaction.objects.filter(
            target=fund,
            type__in=[
                TransactionType.SALE_ISSUANCE,
                TransactionType.CAPITAL_GAIN_ISSUANCE,
                TransactionType.CORRECTION_CREDIT_ISSUANCE,
                TransactionType.PURCHASE_ISSUANCE,  # project as vendor
            ],
            **tx_valid,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        costs = Transaction.objects.filter(
            source=fund,
            type__in=[
                TransactionType.PURCHASE_ISSUANCE,
                TransactionType.EXPENSE_ISSUANCE,
                TransactionType.CAPITAL_LOSS_ISSUANCE,
                TransactionType.CORRECTION_DEBIT_ISSUANCE,
                TransactionType.SALE_ISSUANCE,  # project as client
            ],
            **tx_valid,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        # Adjustment transactions carry no effect flag — the sign lives on Adjustment.effect.
        # Resolve via content_type + object_id subquery.
        adj_ct = ContentType.objects.get_for_model(Adjustment)
        adj_valid = dict(
            deleted_at__isnull=True,
            reversal_of__isnull=True,
            reversed_by__isnull=True,
        )

        def _adj_tx_sum(adj_qs):
            ids = adj_qs.values_list("id", flat=True)
            return Transaction.objects.filter(
                content_type=adj_ct, object_id__in=ids, **tx_valid
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        # Income adjustments: project is the destination of the adjusted operation
        income_adjs = Adjustment.objects.filter(
            **adj_valid,
            operation__destination=self.entity,
            operation__operation_type__in=[OperationType.SALE, OperationType.PURCHASE],
        )
        income += _adj_tx_sum(income_adjs.filter(effect=AdjustmentEffect.INCREASE))
        income -= _adj_tx_sum(income_adjs.filter(effect=AdjustmentEffect.DECREASE))

        # Cost adjustments: project is the source of the adjusted operation
        cost_adjs = Adjustment.objects.filter(
            **adj_valid,
            operation__source=self.entity,
            operation__operation_type__in=[
                OperationType.PURCHASE,
                OperationType.EXPENSE,
                OperationType.SALE,  # project as client
            ],
        )
        costs += _adj_tx_sum(cost_adjs.filter(effect=AdjustmentEffect.INCREASE))
        costs -= _adj_tx_sum(cost_adjs.filter(effect=AdjustmentEffect.DECREASE))

        return income - costs


from django.utils.translation import gettext_lazy as _


class StakeholderRole(models.TextChoices):
    WORKER = "worker", _("Worker")
    CLIENT = "client", _("Client")
    VENDOR = "vendor", _("Vendor")
    SHAREHOLDER = "shareholder", _("Shareholder")


class Stakeholder(ImmutableMixin, BaseModel):
    _immutable_fields = {"parent": {}, "target": {}, "role": {}}

    parent = models.ForeignKey(
        "Entity", on_delete=models.CASCADE, related_name="stakeholders"
    )
    target = models.ForeignKey(
        "Entity", on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=30, choices=StakeholderRole)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    def clean(self) -> None:
        if not self.parent.project and not self.parent.person:
            raise ValidationError(
                "The parent party should be a project or person entity."
            )
        if not self.target.project and not self.target.person:
            raise ValidationError(
                "The target party should be a project or person entity."
            )
        if self.target.project and self.role in ("shareholder", "worker"):
            raise ValidationError(
                "The target party (project) can' assigned as a worker or a shareholder."
            )
        return super().clean()

    def __str__(self):
        return f"{self.target} as {self.get_role_display()} in {self.parent}"


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
    )

    project = models.OneToOneField(
        to="Project",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="entity",
    )

    user = models.OneToOneField(
        to=User, on_delete=models.PROTECT, related_name="entity", null=True, blank=True
    )

    # fund = models.OneToOneField(
    #     to="Fund",
    #     on_delete=models.PROTECT,
    #     null=True,  # allow temproary
    #     blank=True,
    #     related_name="entity",
    # )

    is_internal = models.BooleanField(default=False)

    is_system = models.BooleanField(default=False)
    is_world = models.BooleanField(default=False)

    is_vendor = models.BooleanField(default=False)
    is_client = models.BooleanField(default=False)
    is_worker = models.BooleanField(default=False)
    is_shareholder = models.BooleanField(default=False)

    active = models.BooleanField(default=True)

    @property
    def owner(self):
        a = self.project or self.person
        if a:
            return a
        if self.is_system:
            return Virtual("System", "SYSTEM")
        if self.is_world:
            return Virtual("World", "WORLD")

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
        return f"Entity {self.owner}"

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
                f"Entity must have exactly one identity (Person, Project, System, or World)."
                f"This have {active_count} {identity_sources}"
            )
        if active_count > 1:
            raise ValueError(
                "Entity cannot represent multiple identities simultaneously."
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
                raise ValidationError("System entity already exists.")
        if is_new and self.is_world:
            # Disallow duplicate
            exists = Entity.objects.filter(is_world=True).exists()
            if exists:
                raise ValidationError("World entity already exists.")

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
