"""
Tests for InvoiceItemAdjustment and InvoiceItemAdjustmentLine.

Concern breakdown:
  - InvoiceItemAdjustment  → item-level changes + ProductLedgerEntry sync
  - Adjustment             → financial transactions (created by finalize())
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_adjustment._item_type import InvoiceItemAdjustmentType
from apps.app_adjustment.models import (
    AdjustmentType,
    InvoiceItemAdjustment,
    InvoiceItemAdjustmentLine,
)
from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import (
    InvoiceItem,
    Product,
    ProductLedgerEntry,
    ProductTemplate,
)
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import PurchaseOperation, SaleOperation
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_officer(username="officer"):
    return User.objects.create_user(username=username, password="x", is_staff=True)


def _make_project(name="Farm"):
    return Entity.create(EntityType.PROJECT, name=name)


def _make_vendor(name="Vendor"):
    return Entity.create(EntityType.PERSON, name=name, is_vendor=True)


def _make_client(name="Client"):
    return Entity.create(EntityType.PROJECT, name=name, is_client=True)


def _link_vendor(project_entity, vendor_entity):
    sh = Stakeholder(
        parent=project_entity,
        target=vendor_entity,
        role=StakeholderRole.VENDOR,
        active=True,
    )
    sh.save()


def _link_client(project_entity, client_entity):
    sh = Stakeholder(
        parent=project_entity,
        target=client_entity,
        role=StakeholderRole.CLIENT,
        active=True,
    )
    sh.save()


def _make_purchase_op(
    project_entity, vendor_entity, officer, amount=Decimal("1000.00")
):
    op = PurchaseOperation.objects.create(
        source=project_entity,
        destination=vendor_entity,
        amount=amount,
        operation_type=OperationType.PURCHASE,
        date=date.today(),
        officer=officer,
    )
    return op


def _make_sale_op(client_entity, project_entity, officer, amount=Decimal("1000.00")):
    op = SaleOperation.objects.create(
        source=client_entity,
        destination=project_entity,
        amount=amount,
        operation_type=OperationType.SALE,
        date=date.today(),
        officer=officer,
    )
    return op


def _make_product_template(name="Cattle"):
    return ProductTemplate.objects.create(
        name=name,
        nature=ProductTemplate.Nature.ANIMAL,
        tracking_mode=ProductTemplate.TrackingMode.BATCH,
        default_unit="Head",
    )


def _make_invoice_with_item(operation, template, quantity, unit_price):
    item = InvoiceItem.objects.create(
        operation=operation, product=template, quantity=quantity, unit_price=unit_price
    )
    return item


def _make_product_for_item(template, item, unit_price, quantity=1):
    product = Product.objects.create(
        product_template=template, unit_price=unit_price, quantity=quantity
    )
    product.invoice_items.add(item)
    return product


def _make_item_adj(operation, adj_type, officer, reason=""):
    ia = InvoiceItemAdjustment(
        operation=operation,
        type=adj_type,
        date=date.today(),
        officer=officer,
        reason=reason,
    )
    ia.full_clean()
    ia.save()
    return ia


def _make_line(item_adj, invoice_item, **kwargs):
    line = InvoiceItemAdjustmentLine(
        adjustment=item_adj, invoice_item=invoice_item, **kwargs
    )
    line.full_clean()
    line.save()
    return line


# ---------------------------------------------------------------------------
# FinalizationTest
# ---------------------------------------------------------------------------


class ImmutabilityTest(TestCase):
    """Fields on both models cannot be changed after save."""

    def setUp(self):
        self.officer = _make_officer()
        self.project = _make_project()
        self.vendor = _make_vendor()
        _link_vendor(self.project, self.vendor)
        self.template = _make_product_template()
        self.op = _make_purchase_op(self.project, self.vendor, self.officer)
        self.item = _make_invoice_with_item(
            self.op, self.template, Decimal("10"), Decimal("100.00")
        )

    def test_item_adjustment_operation_is_immutable(self):
        ia = _make_item_adj(
            self.op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        other_op = _make_purchase_op(
            self.project, self.vendor, self.officer, Decimal("200.00")
        )
        ia.operation = other_op
        with self.assertRaises(ValidationError):
            ia.save()

    def test_item_adjustment_type_is_immutable(self):
        ia = _make_item_adj(
            self.op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        ia.type = InvoiceItemAdjustmentType.PURCHASE_ITEM_INCREASE
        with self.assertRaises(ValidationError):
            ia.save()

    def test_line_fields_are_immutable(self):
        ia = _make_item_adj(
            self.op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        line = _make_line(ia, self.item, new_unit_price=Decimal("90.00"))
        line.new_unit_price = Decimal("80.00")
        with self.assertRaises(ValidationError):
            line.save()


# ---------------------------------------------------------------------------
# ReversalTest
# ---------------------------------------------------------------------------
