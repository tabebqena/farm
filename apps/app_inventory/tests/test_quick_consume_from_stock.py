"""Tests for the one-step "Consume from stock" view (``quick_consume``).

A single POST from the stock detail page must create the full consumption
pipeline by reusing ``ConsumptionOperation.create(...)``:
ConsumptionOperation + invoice item + auto movement line +
``CONSUMPTION_ISSUANCE`` + ``CONSUMPTION_PAYMENT`` transactions +
``CONSUMPTION_MOVEMENT`` ledger entry, and mark the product ``CONSUMED``.
"""

from datetime import date
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import (
    InventoryMovementLine,
    Product,
    ProductLedgerEntry,
    ProductTemplate,
)
from apps.app_inventory.tests.general import (
    make_entity,
    make_invoice_item,
    make_operation,
    make_project_entity,
    make_user,
)
from apps.app_operation.models.operation import Operation
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import PurchaseOperation
from apps.app_operation.tests.base import assert_tx_types
from apps.app_transaction.transaction_type import TransactionType


class QuickConsumeFromStockTest(TestCase):
    """POST-driven quick-consume from the stock detail page."""

    def setUp(self):
        self.client = Client()
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.officer_user = make_user(username="officer_quick")
        self.project_entity = make_project_entity("Test Farm Project")
        self.vendor = make_entity(EntityType.PERSON, "Vendor", is_vendor=True)
        Stakeholder.objects.create(
            parent=self.project_entity,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        self.template = ProductTemplate.objects.create(
            name="Feed Mix",
            nature=ProductTemplate.Nature.FEED,
            sub_category="Feed",
            default_unit="Kg",
            minimum_quantity=Decimal("1.00"),
        )

    def _make_moved_product(self, qty=Decimal("5.00"), price=Decimal("100.00")):
        """Return an ACTIVE, physically-moved product owned by the project."""
        purchase = make_operation(
            self.project_entity,
            self.vendor,
            self.officer_user,
            PurchaseOperation,
            OperationType.PURCHASE,
            amount=(qty * price).quantize(Decimal("0.01")),
        )
        item = make_invoice_item(purchase, self.template, qty, price)
        product = Product.objects.create(
            product_template=self.template,
            entity=self.project_entity,
            unit_price=price,
            quantity=int(qty),
        )
        product.invoice_items.add(item)
        InventoryMovementLine.objects.create(
            operation=purchase,
            invoice_item=item,
            product=product,
            quantity=qty,
            date=date.today(),
            officer=self.officer_user,
        )
        return product

    def _post_consume(self, product, qty=Decimal("5.00"), price=Decimal("100.00"), **extra):
        data = {
            "product_id": str(product.pk),
            "quantity": str(qty),
            "unit_price": str(price),
        }
        data.update(extra)
        return self.client.post(
            reverse("quick_consume", kwargs={"entity_pk": self.project_entity.pk}),
            data,
        )

    def _consumption_count(self):
        """Count ConsumptionOperation rows only (proxy managers see all ops)."""
        return Operation.objects.filter(
            operation_type=OperationType.CONSUMPTION
        ).count()

    def test_quick_consume_creates_full_pipeline(self):
        """One POST creates the operation, movement line, transactions, ledger
        entry, and marks the product consumed."""
        self.client.login(username="officer_quick", password="testpass")
        product = self._make_moved_product()

        response = self._post_consume(product)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response, reverse("stock_detail", kwargs={"entity_pk": self.project_entity.pk})
        )

        op = Operation.objects.get(operation_type=OperationType.CONSUMPTION)
        self.assertEqual(op.source, self.project_entity)
        self.assertEqual(op.destination, self.system_entity)
        self.assertEqual(op.amount, Decimal("500.00"))

        # Movement line auto-created for the selected product
        self.assertEqual(op.movement_lines.count(), 1)
        ml = op.movement_lines.first()
        self.assertEqual(ml.product, product)
        self.assertEqual(ml.quantity, Decimal("5.00"))

        # Issuance + payment transactions
        assert_tx_types(
            self,
            op,
            {
                TransactionType.CONSUMPTION_ISSUANCE: 1,
                TransactionType.CONSUMPTION_PAYMENT: 1,
            },
        )

        # CONSUMPTION_MOVEMENT ledger entry with correct deltas
        movement = ProductLedgerEntry.objects.get(
            product=product,
            entry_type=ProductLedgerEntry.EntryType.CONSUMPTION_MOVEMENT,
        )
        self.assertEqual(movement.quantity_delta, Decimal("-5.00"))
        self.assertEqual(movement.value_delta, Decimal("-500.00"))

        # Product is consumed
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.CONSUMED)

    def test_stock_detail_renders_quick_consume_form(self):
        """An active FEED product renders the inline quick-consume form on the
        stock detail page (its action posts to the ``quick_consume`` view)."""
        self.client.login(username="officer_quick", password="testpass")
        product = self._make_moved_product()

        response = self.client.get(
            reverse("stock_detail", kwargs={"entity_pk": self.project_entity.pk}),
            {"tab": "live"},
        )

        self.assertEqual(response.status_code, 200)
        consume_url = reverse(
            "quick_consume", kwargs={"entity_pk": self.project_entity.pk}
        )
        self.assertContains(response, f'action="{consume_url}"')
        self.assertContains(response, f'name="product_id" value="{product.pk}"')

    def test_quick_consume_partial_consumption(self):
        """Consuming part of the stock leaves the remainder physically present."""
        self.client.login(username="officer_quick", password="testpass")
        product = self._make_moved_product(qty=Decimal("5.00"))

        response = self._post_consume(product, qty=Decimal("2.00"))

        self.assertEqual(response.status_code, 302)
        remaining = ProductLedgerEntry.state_as_of(product, date.today())["quantity"]
        self.assertEqual(remaining, Decimal("3.00"))
        self.assertEqual(self._consumption_count(), 1)

    def test_quick_consume_over_consumption_is_rejected(self):
        """Cannot consume more than physically on hand — no operation is created."""
        self.client.login(username="officer_quick", password="testpass")
        product = self._make_moved_product(qty=Decimal("5.00"))

        response = self._post_consume(product, qty=Decimal("6.00"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._consumption_count(), 0)
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.ACTIVE)

    def test_quick_consume_requires_officer(self):
        """Non-officer users are rejected before any side-effect runs."""
        non_officer = make_user(username="non_officer_quick", is_staff=False)
        self.client.login(username="non_officer_quick", password="testpass")
        product = self._make_moved_product()

        response = self._post_consume(product)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._consumption_count(), 0)
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.ACTIVE)

    def test_quick_consume_rejects_non_consumable_nature(self):
        """ANIMAL templates cannot be consumed — no operation is created."""
        self.client.login(username="officer_quick", password="testpass")
        animal_template = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            default_unit="Head",
        )
        purchase = make_operation(
            self.project_entity,
            self.vendor,
            self.officer_user,
            PurchaseOperation,
            OperationType.PURCHASE,
            amount=Decimal("500.00"),
        )
        item = make_invoice_item(purchase, animal_template, Decimal("5.00"), Decimal("100.00"))
        product = Product.objects.create(
            product_template=animal_template,
            entity=self.project_entity,
            unit_price=Decimal("100.00"),
            quantity=5,
        )
        product.invoice_items.add(item)
        InventoryMovementLine.objects.create(
            operation=purchase,
            invoice_item=item,
            product=product,
            quantity=Decimal("5.00"),
            date=date.today(),
            officer=self.officer_user,
        )

        response = self._post_consume(product)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._consumption_count(), 0)

    def test_quick_consume_rejects_non_consumable_flag(self):
        """A non-ANIMAL (FEED) template with can_be_consumed=False is rejected
        even though its nature otherwise allows consumption."""
        self.client.login(username="officer_quick", password="testpass")
        feed = ProductTemplate.objects.create(
            name="Restricted Feed",
            nature=ProductTemplate.Nature.FEED,
            default_unit="Kg",
            can_be_consumed=False,
        )
        purchase = make_operation(
            self.project_entity,
            self.vendor,
            self.officer_user,
            PurchaseOperation,
            OperationType.PURCHASE,
            amount=Decimal("500.00"),
        )
        item = make_invoice_item(purchase, feed, Decimal("5.00"), Decimal("100.00"))
        product = Product.objects.create(
            product_template=feed,
            entity=self.project_entity,
            unit_price=Decimal("100.00"),
            quantity=5,
        )
        product.invoice_items.add(item)
        InventoryMovementLine.objects.create(
            operation=purchase,
            invoice_item=item,
            product=product,
            quantity=Decimal("5.00"),
            date=date.today(),
            officer=self.officer_user,
        )

        response = self._post_consume(product)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._consumption_count(), 0)

    def test_quick_consume_rejects_product_not_in_entity(self):
        """A product owned by another entity cannot be consumed from this stock."""
        self.client.login(username="officer_quick", password="testpass")
        other_project = make_project_entity("Other Farm Project")
        product = Product.objects.create(
            product_template=self.template,
            entity=other_project,
            unit_price=Decimal("100.00"),
            quantity=5,
        )

        response = self._post_consume(product)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._consumption_count(), 0)
