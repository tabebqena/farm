"""Tests for SaleOperation.create_from_session() — the sale must AFFECT the
seller's EXISTING product (SALE_MOVEMENT line) instead of minting a fresh
SOLD product. No new product is ever created by a sale."""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import (
    InventoryMovementLine,
    Product,
    ProductTemplate,
)
from apps.app_inventory.stock import movement_state
from apps.app_inventory.tests.general import make_invoice_item, make_operation, make_product
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import PurchaseOperation, SaleOperation
from apps.app_operation.tests.base import (
    inject_person_fund,
    inject_project_fund,
    make_officer,
    make_project,
    make_stakeholder,
)
from apps.app_transaction.transaction_type import TransactionType


def _make_commodity_template(name="Feed"):
    return ProductTemplate.objects.create(
        name=name,
        nature=ProductTemplate.Nature.FEED,
        sub_category="Feed",
        tracking_mode=ProductTemplate.TrackingMode.COMMODITY,
        default_unit="Kg",
        minimum_quantity=Decimal("0.01"),
    )


class SaleCreateFromSessionStockTest(TestCase):
    """The sale affects the seller's existing on-hand product."""

    def setUp(self):
        self.system = Entity.create(EntityType.SYSTEM)
        self.world = Entity.create(EntityType.WORLD)
        self.officer = make_officer()
        self.project = make_project("Farm Project")
        self.client_entity = Entity.create(
            EntityType.PERSON, name="Buyer Corp", is_client=True, active=True
        )
        make_stakeholder(
            self.project,
            self.client_entity,
            role=StakeholderRole.CLIENT,
            active=True,
        )
        inject_project_fund(self.system, self.project, Decimal("5000.00"), self.officer)
        inject_person_fund(
            self.world, self.client_entity, Decimal("5000.00"), self.officer
        )

        self.vendor = Entity.create(
            EntityType.PERSON, name="Vendor", is_vendor=True, active=True
        )
        make_stakeholder(
            self.project, self.vendor, role=StakeholderRole.VENDOR, active=True
        )

        self.template = _make_commodity_template()
        self.template.entities.add(self.project)

    def _receive_product(self, qty=Decimal("10.00"), price=Decimal("50.00")):
        """Physically receive *qty* of a product owned by the project, so it is
        present on-hand in the ledger (PURCHASE_MOVEMENT)."""
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
            amount=(qty * price).quantize(Decimal("0.01")),
        )
        item = make_invoice_item(purchase, self.template, quantity=qty, unit_price=price)
        product = make_product(self.template, entity=self.project, quantity=int(qty))
        InventoryMovementLine.objects.create(
            operation=purchase,
            invoice_item=item,
            product=product,
            quantity=qty,
            date=date.today(),
            officer=self.officer,
            notes="",
            group_key="setup",
        )
        return product

    def _session_data(self, product, quantity="4.00", unit_price="100.00"):
        return {
            "date": date.today().isoformat(),
            "client_id": self.client_entity.pk,
            "description": "Test sale",
            "total_amount": (Decimal(quantity) * Decimal(unit_price)).quantize(
                Decimal("0.01")
            ),
            "amount_paid": "0",
            "items": [
                {
                    "product_id": product.pk,
                    "description": "",
                    "quantity": quantity,
                    "unit_price": unit_price,
                }
            ],
        }

    def test_sale_affects_existing_product_no_mint(self):
        """Selling part of an existing product: movement against it, no new
        Product row, physical presence reduced."""
        product = self._receive_product(qty=Decimal("10.00"))
        product_count_before = Product.objects.count()

        op = SaleOperation.create_from_session(
            project=self.project,
            session_data=self._session_data(product, quantity="4.00"),
            officer=self.officer,
        )

        # No new product minted — the existing one is affected.
        self.assertEqual(Product.objects.count(), product_count_before)
        # One SALE_MOVEMENT line against the existing product.
        lines = InventoryMovementLine.objects.filter(operation=op)
        self.assertEqual(lines.count(), 1)
        self.assertEqual(lines.first().product, product)
        self.assertEqual(lines.first().quantity, Decimal("4.00"))
        # The product is linked to the sale item.
        product.refresh_from_db()
        self.assertTrue(product.invoice_items.filter(operation=op).exists())
        # Movement-based status: a partial sale (4 of 10) leaves remaining
        # presence, so the product stays ACTIVE.
        self.assertEqual(product.status, Product.Status.ACTIVE)
        # Physical presence reduced: 10 - 4 = 6.
        state = movement_state(product, as_of=date.today())
        self.assertEqual(state["quantity"], Decimal("6.00"))

    def test_sale_full_disposal_leaves_zero(self):
        product = self._receive_product(qty=Decimal("5.00"))
        SaleOperation.create_from_session(
            project=self.project,
            session_data=self._session_data(product, quantity="5.00"),
            officer=self.officer,
        )
        self.assertEqual(
            movement_state(product, as_of=date.today())["quantity"],
            Decimal("0.00"),
        )
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.SOLD)

    def test_sale_individual_animal_affected(self):
        template = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            tracking_mode=ProductTemplate.TrackingMode.INDIVIDUAL,
            default_unit="Head",
        )
        template.entities.add(self.project)
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
            amount=Decimal("100.00"),
        )
        item = make_invoice_item(
            purchase, template, quantity=Decimal("1.00"), unit_price=Decimal("100.00")
        )
        animal = make_product(
            template, entity=self.project, quantity=1, unit_price=Decimal("100.00")
        )
        InventoryMovementLine.objects.create(
            operation=purchase,
            invoice_item=item,
            product=animal,
            quantity=Decimal("1.00"),
            date=date.today(),
            officer=self.officer,
            notes="",
            group_key="setup",
        )

        op = SaleOperation.create_from_session(
            project=self.project,
            session_data=self._session_data(
                animal, quantity="1.00", unit_price="150.00"
            ),
            officer=self.officer,
        )
        animal.refresh_from_db()
        self.assertEqual(animal.status, Product.Status.SOLD)
        lines = InventoryMovementLine.objects.filter(operation=op)
        self.assertEqual(lines.count(), 1)
        self.assertEqual(lines.first().product, animal)
        self.assertEqual(lines.first().quantity, Decimal("1.00"))

    def test_sale_over_sell_rejected_atomically(self):
        product = self._receive_product(qty=Decimal("3.00"))
        with self.assertRaises(ValidationError):
            SaleOperation.create_from_session(
                project=self.project,
                session_data=self._session_data(product, quantity="10.00"),
                officer=self.officer,
            )
        # Atomic rollback: no sale operation was persisted.
        self.assertFalse(
            SaleOperation.objects.filter(
                source=self.client_entity, destination=self.project
            ).exists()
        )

    def test_sale_rejects_product_not_owned_by_project(self):
        other = Entity.create(EntityType.PROJECT, name="Other Project")
        self.template.entities.add(other)
        product = make_product(self.template, entity=other, quantity=5)
        with self.assertRaises(ValidationError):
            SaleOperation.create_from_session(
                project=self.project,
                session_data=self._session_data(product, quantity="1.00"),
                officer=self.officer,
            )

    def test_sale_issuance_transaction_created(self):
        product = self._receive_product(qty=Decimal("2.00"))
        op = SaleOperation.create_from_session(
            project=self.project,
            session_data=self._session_data(product, quantity="2.00"),
            officer=self.officer,
        )
        self.assertTrue(
            op.get_all_transactions()
            .filter(type=TransactionType.SALE_ISSUANCE)
            .exists()
        )

    def test_internal_client_receives_active_product(self):
        """An internal-client sale transfers the goods: the buyer receives an
        ACTIVE product (with an inbound receipt); the seller's product keeps
        its remaining presence (partial 4-of-10 transfer → ACTIVE)."""
        self.client_entity.is_internal = True
        self.client_entity.save()
        seller_product = self._receive_product(qty=Decimal("10.00"))
        product_count_before = Product.objects.count()

        op = SaleOperation.create_from_session(
            project=self.project,
            session_data=self._session_data(seller_product, quantity="4.00"),
            officer=self.officer,
        )

        # Seller's product keeps its remaining presence (10 - 4 = 6) → ACTIVE.
        seller_product.refresh_from_db()
        self.assertEqual(seller_product.status, Product.Status.ACTIVE)
        # A buyer copy exists, owned by the internal client, ACTIVE (received).
        buyer_products = Product.objects.filter(
            entity=self.client_entity, product_template=self.template
        )
        self.assertEqual(buyer_products.count(), 1)
        buyer = buyer_products.first()
        self.assertEqual(buyer.status, Product.Status.ACTIVE)
        # The buyer copy has an inbound receipt movement (PURCHASE_MOVEMENT +).
        self.assertTrue(
            buyer.movement_lines.filter(operation=op, reversal_of__isnull=True).exists()
        )
        # The buyer is physically present for the received quantity.
        self.assertEqual(
            movement_state(buyer, as_of=date.today())["quantity"],
            Decimal("4.00"),
        )
        # Exactly one new product row was created (the buyer copy).
        self.assertEqual(Product.objects.count(), product_count_before + 1)

    def test_external_client_gets_no_buyer_copy(self):
        """An external client does not receive a product — only the seller's
        existing product is affected."""
        seller_product = self._receive_product(qty=Decimal("10.00"))
        SaleOperation.create_from_session(
            project=self.project,
            session_data=self._session_data(seller_product, quantity="4.00"),
            officer=self.officer,
        )
        self.assertFalse(
            Product.objects.filter(entity=self.client_entity).exists()
        )

    def test_internal_client_receipt_movement_can_be_reversed(self):
        """The buyer's receipt movement is reversible (negated ledger row)."""
        self.client_entity.is_internal = True
        self.client_entity.save()
        seller_product = self._receive_product(qty=Decimal("10.00"))
        op = SaleOperation.create_from_session(
            project=self.project,
            session_data=self._session_data(seller_product, quantity="4.00"),
            officer=self.officer,
        )
        buyer = Product.objects.get(
            entity=self.client_entity, product_template=self.template
        )
        receipt_line = buyer.movement_lines.get(
            operation=op, reversal_of__isnull=True
        )
        rev = receipt_line.reverse(officer=self.officer)
        self.assertIsNotNone(rev.pk)
        # The buyer's receipt nets back to zero after reversal.
        self.assertEqual(
            movement_state(buyer, as_of=date.today())["quantity"],
            Decimal("0.00"),
        )
        # The receipt now has a reversal line (the original is marked reversed).
        self.assertTrue(
            buyer.movement_lines.filter(
                operation=op, reversal_of__isnull=False
            ).exists()
        )
