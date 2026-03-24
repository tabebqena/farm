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

    # def clean(self) -> None:
    #     if getattr(self, "entity", None) is None:
    #         raise ValidationError("You should link fund object to an entity.")
    #     return super().clean()


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
    can_pay = models.BooleanField(default=True)
    active = models.BooleanField(default=True)

    # stakeholders = models.ManyToManyField(
    #     to="self",
    #     symmetrical=False,  # Important: Project A owns Person B, but Person B doesn't own Project A
    #     related_name="associated_to",
    #     # related_name="entity"
    # )

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
            self.can_pay = False
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
        can_pay=True,
        active=True,
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
            e.can_pay = False
            e.fund = None

            e.save()
            if fund is None:
                fund = Fund.objects.create(entity=e)
            e.fund = fund
            e.can_pay = can_pay
            e.active = active
            e.save()
            return e
