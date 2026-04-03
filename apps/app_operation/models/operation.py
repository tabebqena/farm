import logging
from typing import List

from django.db import models
from django.db.models import Q, Sum

from apps.app_base.mixins import (
    AdjustableMixin,
    AmountCleanMixin,
    ImmutableMixin,
    LinkedIssuanceTransactionMixin,
    LinkedPaymentTransactionMixin,
    LinkedRePaymentTransactionMixin,
    OfficerMixin,
)
from apps.app_base.models import BaseModel, ReversableModel
from apps.app_transaction.transaction_type import TransactionType

from .managers import AllOperationManager, OperationManager
from .operation_type import OperationType

logger = logging.getLogger(__name__)

# TODO use database level constrains for data integrity.
# TODO add financial period closing
# TODO: "Financial Statement" method
# TODO: Integrity check method


class Operation(
    ImmutableMixin,
    AdjustableMixin,
    AmountCleanMixin,
    LinkedIssuanceTransactionMixin,
    LinkedPaymentTransactionMixin,
    LinkedRePaymentTransactionMixin,
    OfficerMixin,
    ReversableModel,
    BaseModel,
):
    """
    Central financial operation record.
    All type-specific logic lives in proxy subclasses.
    This class holds only shared fields and shared behavior.
    """

    _immutable_fields = {"source": {}, "destination": {}, "amount": {}}
    _amount_name = "amount"
    _adjustments_related_name = "adjustments"

    source = models.ForeignKey(
        to="app_entity.Entity",
        on_delete=models.PROTECT,
        related_name="operations_outgoing",
    )
    destination = models.ForeignKey(
        "app_entity.Entity",
        on_delete=models.PROTECT,
        related_name="operations_incoming",
    )
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    operation_type = models.CharField(max_length=30, choices=OperationType.choices)
    date = models.DateField()
    description = models.TextField(blank=True)
    officer = models.ForeignKey(
        "app_entity.Entity",
        on_delete=models.PROTECT,
        related_name="operations_supervised",
    )

    objects = OperationManager()
    all_objects = AllOperationManager()

    # Config defaults — overridden as class attrs on each proxy model
    url_str: str | None = None
    label: str | None = None
    _source_role: str | None = None
    _dest_role: str | None = None
    can_pay: bool = False
    is_partially_payable: bool = False
    has_category: bool = False
    category_required: bool = False
    has_repayment: bool = False
    repayment_label: str | None = None
    has_invoice: bool = False
    theme_color: str = "danger"
    theme_icon: str = "bi-box-arrow-up-right"

    class Meta:
        verbose_name = "Operation"
        verbose_name_plural = "Operations"
        ordering = ["-date", "-created_at"]

    # ------------------------------------------------------------------
    # Request resolution
    # ------------------------------------------------------------------

    @classmethod
    def resolve_request(cls, url_pk, request) -> dict:
        """
        Resolves a request into a unified config + entity dict.
        Call on the proxy class: e.g. PurchaseOperation.resolve_request(pk, request)
        """
        from django.shortcuts import get_object_or_404
        from apps.app_entity.models import Entity

        url_entity = get_object_or_404(Entity, pk=url_pk)
        source_role = cls._source_role
        dest_role = cls._dest_role

        world_entity = None
        if source_role == "world" or dest_role == "world":
            world_entity = Entity.objects.filter(is_world=True).first()
        system_entity = None
        if source_role == "system" or dest_role == "system":
            system_entity = Entity.objects.filter(is_system=True).first()

        secondary_pk = request.POST.get("secondary_entity")
        secondary_entity = get_object_or_404(Entity, pk=secondary_pk) if secondary_pk else None

        def resolve(role):
            if role == "world":
                return world_entity
            if role == "system":
                return system_entity
            if role == "url":
                return url_entity
            if role == "post":
                return secondary_entity
            return None

        return {
            "proxy_cls": cls,
            "label": cls.label,
            "url_str": cls.url_str,
            "source": source_role,
            "dest": dest_role,
            "can_pay": cls.can_pay,
            "is_partially_payable": cls.is_partially_payable,
            "has_category": cls.has_category,
            "category_required": cls.category_required,
            "has_repayment": cls.has_repayment,
            "has_invoice": cls.has_invoice,
            "repayment_transaction_type": getattr(cls, "_repayment_transaction_type", None),
            "theme_color": cls.theme_color,
            "theme_icon": cls.theme_icon,
            "url_entity": url_entity,
            "secondary_entity": secondary_entity,
            "source_entity": resolve(source_role),
            "dest_entity": resolve(dest_role),
        }

    @classmethod
    def get_related_entities(cls, url_entity, config):
        from apps.app_entity.models import Entity
        config_dest = config["dest"]
        if config_dest in ["world", "url"]:
            return []
        elif config_dest == "post":
            return Entity.objects.all()
        return []

    # ------------------------------------------------------------------
    # Reversal helpers
    # ------------------------------------------------------------------

    @property
    def _reversable_transaction_types(self) -> List[TransactionType]:
        rv = []
        if self._issuance_transaction_type:
            rv.append(self._issuance_transaction_type)
        if self._payment_transaction_type:
            rv.append(self._payment_transaction_type)
        return rv

    @property
    def _implicit_reversable_transaction_types(self) -> List[TransactionType]:
        rv = []
        if self._issuance_transaction_type:
            rv.append(self._issuance_transaction_type)
        if self._is_one_shot_operation and self._payment_transaction_type:
            rv.append(self._payment_transaction_type)
        return rv

    # ------------------------------------------------------------------
    # Cash flow
    # ------------------------------------------------------------------

    def get_cash_flow_balance(self):
        valid_txs = self.get_all_transactions().filter(
            reversal_of__isnull=True,
            reversed_by__isnull=True,
        )
        payment_type = self._payment_transaction_type
        cash_movements = valid_txs.filter(
            Q(type=payment_type) | Q(type=TransactionType.LOAN_REPAYMENT)
        )
        total_payment = (
            cash_movements.filter(type=payment_type).aggregate(Sum("amount"))[
                "amount__sum"
            ]
            or 0
        )
        total_repayment = (
            cash_movements.filter(type=TransactionType.LOAN_REPAYMENT).aggregate(
                Sum("amount")
            )["amount__sum"]
            or 0
        )
        return total_payment - total_repayment

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def clean(self):
        return super().clean()

    def __str__(self):
        return (
            f"Operation {self.operation_type}: "
            f"{self.amount} from {self.source} to {self.destination}"
        )
