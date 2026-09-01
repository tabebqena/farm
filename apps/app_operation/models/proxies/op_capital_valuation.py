from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation, StockEventMixin
from apps.app_operation.models.operation_type import OperationType


class CapitalValuationOperation(StockEventMixin, Operation):
    """Single proxy for Capital Gain (system -> project) and Capital Loss
    (project -> system).

    Both operation types share this one proxy class; per-type configuration
    (URL slug, label, roles, validation) is dispatched on the row's
    ``operation_type`` via ``_VARIANT_CONFIG``. No behavior differs from the
    two former proxies (CapitalGainOperation / CapitalLossOperation).
    """

    # Shared non-accounting config comes from ``StockEventMixin``; only the
    # value-only overrides remain here (no invoice items — the valuation is a
    # ``ProductCapitalValuation`` row, never an ``InvoiceItem``).
    has_invoice = False
    has_capital_valuation = True

    # Per-type configuration keyed by operation type.
    _VARIANT_CONFIG = {
        OperationType.CAPITAL_GAIN: {
            "url_str": "capital-gain",
            "label": "Capital Gain Issuance",
            "_source_role": "system",
            "_dest_role": "url",
            "verbose_name": "Capital Gain",
        },
        OperationType.CAPITAL_LOSS: {
            "url_str": "capital-loss",
            "label": "Capital Loss Issuance",
            "_source_role": "url",
            "_dest_role": "system",
            "verbose_name": "Capital Loss",
        },
    }

    # Both URL slugs resolve to this single proxy class.
    url_strs = ("capital-gain", "capital-loss")

    class Meta:
        proxy = True
        verbose_name = "Capital Valuation"

    # ------------------------------------------------------------------
    # Class-level helpers (registry / create-view resolution)
    # ------------------------------------------------------------------

    @classmethod
    def operation_type_for_url(cls, url_str):
        """Return the operation type for a URL slug, or None if unknown."""
        for op_type, cfg in cls._VARIANT_CONFIG.items():
            if cfg["url_str"] == url_str:
                return op_type
        return None

    @classmethod
    def _type_config(cls, operation_type):
        """Per-type config dict used by ``Operation.resolve_request``."""
        return cls._VARIANT_CONFIG.get(operation_type, {})

    # ------------------------------------------------------------------
    # Instance-level per-type dispatch
    # ------------------------------------------------------------------

    def _variant(self):
        return self._VARIANT_CONFIG[self.operation_type]

    @property
    def label(self):
        return self._variant()["label"]

    @property
    def _source_role(self):
        return self._variant()["_source_role"]

    @property
    def _dest_role(self):
        return self._variant()["_dest_role"]

    def clean_source(self):
        if self.operation_type == OperationType.CAPITAL_GAIN:
            if not self.source.is_system:
                raise ValidationError(
                    "Capital Gain source must be the System entity."
                )
        else:
            if not self.source.is_project:
                raise ValidationError(
                    "Capital Loss source must be a Project entity."
                )

    def clean_destination(self):
        if self.operation_type == OperationType.CAPITAL_GAIN:
            if not self.destination.is_project:
                raise ValidationError(
                    "Capital Gain destination must be a Project entity."
                )
        else:
            if not self.destination.is_system:
                raise ValidationError(
                    "Capital Loss destination must be the System entity."
                )

    def add_valuation(self, product, amount, officer=None, notes=""):
        """
        Link *product* to a value-only capital valuation of *amount* (signed:
        positive for a gain, negative for a loss).

        The operation must already be saved. Creates a ``ProductCapitalValuation``
        row — no ``InvoiceItem`` and no ``InventoryMovementLine`` are created
        (the valuation is value-only). Guards (ownership, template compatibility,
        product active, signed direction) are enforced by the row's ``clean()``.
        """
        from decimal import Decimal

        from apps.app_inventory.models import ProductCapitalValuation

        entry = ProductCapitalValuation(
            operation=self,
            product=product,
            amount=Decimal(amount),
            date=self.date,
            notes=notes,
            officer=officer,
        )
        entry.full_clean()
        entry.save()
        return entry

    @classmethod
    def create_with_valuation(
        cls, *, product, new_unit_price, date, description, officer, project
    ):
        """
        Evaluate *product* at *new_unit_price* and record the capital
        gain/loss operation inside one atomic block.

        Computes the valuation delta (via ``product.compute_valuation_delta``),
        guards ownership, and creates the operation (choosing CAPITAL_GAIN vs
        CAPITAL_LOSS from the delta sign) plus its ``ProductCapitalValuation``
        row. Returns ``(op, entry, delta)``, or ``None`` when there is no
        material change (``abs(delta) < 0.01``) so the caller can show a
        friendly message.
        """
        from decimal import Decimal

        from django.db import transaction
        from django.utils.translation import gettext as _

        from apps.app_entity.models import Entity, EntityType

        valuation = product.compute_valuation_delta(new_unit_price)
        delta = valuation["delta"]
        if abs(delta) < Decimal("0.01"):
            return None

        # Ownership guard (defense-in-depth — the evaluation form queryset
        # already restricts choices to entity=project): never record a
        # gain/loss on another entity's asset. The valuation row's clean()
        # re-checks it at the model layer.
        if product.entity_id != project.id:
            raise ValidationError(
                _(
                    "Product '%(p)s' does not belong to '%(entity)s' "
                    "and cannot be evaluated."
                )
                % {"p": product, "entity": project}
            )

        # The shared CapitalValuationOperation proxy serves both directions:
        # pick the variant from the delta sign.
        op_type = (
            OperationType.CAPITAL_GAIN if delta > 0 else OperationType.CAPITAL_LOSS
        )
        system_entity = Entity.objects.filter(
            entity_type=EntityType.SYSTEM
        ).first()
        if op_type == OperationType.CAPITAL_GAIN:
            source, destination = system_entity, project
        else:
            source, destination = project, system_entity

        amount = abs(delta).quantize(Decimal("0.01"))
        with transaction.atomic():
            op = cls.create(
                operation_type=op_type,
                source=source,
                destination=destination,
                amount=amount,
                date=date,
                description=description,
                officer=officer,
                amount_paid=Decimal("0"),
                project=project,
            )
            entry = op.add_valuation(
                product=product,
                amount=delta.quantize(Decimal("0.01")),
                officer=officer,
            )
        return op, entry, delta
