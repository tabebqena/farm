from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from django.test import TestCase

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import (
    InventoryMovementLine,
    ProductLedgerEntry,
    ProductTemplate,
)
from apps.app_inventory.tests.general import (
    make_entity,
    make_invoice_item,
    make_operation,
    make_product,
    make_product_template,
    make_project_entity,
    make_user,
)
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import (
    BirthOperation,
    CapitalGainOperation,
    CapitalLossOperation,
    ConsumptionOperation,
    DeathOperation,
    PurchaseOperation,
    SaleOperation,
)


class ProductLedgerEntryTest(TestCase):
    def setUp(self):
        self.officer = make_user()
        self.system = Entity.create(EntityType.SYSTEM)
        self.vendor = make_entity(EntityType.PERSON, "Vendor", is_vendor=True)
        self.project = make_project_entity("Farm")
        Stakeholder.objects.create(
            parent=self.project,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        self.client = make_entity(EntityType.PERSON, "Client", is_client=True)
        Stakeholder.objects.create(
            parent=self.project,
            target=self.client,
            active=True,
            role=StakeholderRole.CLIENT,
        )
        self.template = make_product_template()
        self.template.entities.add(self.project)
        self.product = make_product(self.template)

    def _make_operation_with_item(
        self,
        proxy_class,
        op_type,
        source,
        destination,
        qty=Decimal("5.00"),
        price=Decimal("100"),
    ):
        """Build op → item, link self.product to the item, return the operation."""
        op = make_operation(source, destination, self.officer, proxy_class, op_type)
        item = make_invoice_item(op, self.template, qty, price)
        self.product.invoice_items.add(item)
        return op

    def test_consumption_valued_at_purchase_price(self):
        """Fix 9: outbound movements are valued at the product's carried cost,
        so 100 kg @ $2 then consuming 30 kg leaves 70 kg / $140."""
        feed = ProductTemplate.objects.create(
            name="Feed Mix",
            nature=ProductTemplate.Nature.FEED,
            sub_category="Feed",
            default_unit="Kg",
        )
        purchase = make_operation(
            self.project,
            self.vendor,
            self.officer,
            PurchaseOperation,
            OperationType.PURCHASE,
            amount=Decimal("200.00"),
        )
        p_item = make_invoice_item(purchase, feed, Decimal("100.00"), Decimal("2.00"))
        product = make_product(feed, Decimal("2.00"), 100, entity=self.project)
        p_item.products.add(product)
        InventoryMovementLine.objects.create(
            operation=purchase,
            invoice_item=p_item,
            product=product,
            quantity=Decimal("100.00"),
            date=date.today(),
            officer=self.officer,
        )

        consumption = make_operation(
            self.project,
            self.system,
            self.officer,
            ConsumptionOperation,
            OperationType.CONSUMPTION,
            amount=Decimal("60.00"),
        )
        c_item = make_invoice_item(consumption, feed, Decimal("30.00"), Decimal("2.00"))
        c_item.products.add(product)
        InventoryMovementLine.objects.create(
            operation=consumption,
            invoice_item=c_item,
            product=product,
            quantity=Decimal("30.00"),
            date=date.today(),
            officer=self.officer,
        )

        state = ProductLedgerEntry.state_as_of(product, date.today())
        self.assertEqual(state["quantity"], Decimal("70.00"))
        self.assertEqual(state["value"], Decimal("140.00"))

    # --- record() — all six operation types ---

    def test_record_purchase(self):
        op = self._make_operation_with_item(
            PurchaseOperation, OperationType.PURCHASE, self.project, self.vendor
        )
        created, skipped = ProductLedgerEntry.record(op)
        self.assertEqual((created, skipped), (1, 0))
        # Issuance entries are written per invoice_item with product=None.
        entry = ProductLedgerEntry.objects.get(invoice_item=op.items.first())
        self.assertEqual(entry.entry_type, ProductLedgerEntry.EntryType.PURCHASE_ISSUANCE)
        self.assertEqual(entry.quantity_delta, Decimal("5.00"))
        self.assertEqual(entry.value_delta, Decimal("500.00"))

    def test_record_sale(self):
        op = self._make_operation_with_item(
            SaleOperation, OperationType.SALE, self.client, self.project
        )
        ProductLedgerEntry.record(op)
        entry = ProductLedgerEntry.objects.get(invoice_item=op.items.first())
        self.assertEqual(entry.entry_type, ProductLedgerEntry.EntryType.SALE_ISSUANCE)
        self.assertEqual(entry.quantity_delta, Decimal("-5.00"))
        self.assertEqual(entry.value_delta, Decimal("-500.00"))

    def test_record_birth(self):
        op = self._make_operation_with_item(
            BirthOperation, OperationType.BIRTH, self.system, self.project
        )
        ProductLedgerEntry.record(op)
        entry = ProductLedgerEntry.objects.get(invoice_item=op.items.first())
        self.assertEqual(entry.entry_type, ProductLedgerEntry.EntryType.BIRTH_ISSUANCE)
        self.assertEqual(entry.quantity_delta, Decimal("5.00"))
        self.assertEqual(entry.value_delta, Decimal("500.00"))

    def test_record_death(self):
        op = self._make_operation_with_item(
            DeathOperation, OperationType.DEATH, self.project, self.system
        )
        ProductLedgerEntry.record(op)
        entry = ProductLedgerEntry.objects.get(invoice_item=op.items.first())
        self.assertEqual(entry.entry_type, ProductLedgerEntry.EntryType.DEATH_ISSUANCE)
        self.assertEqual(entry.quantity_delta, Decimal("-5.00"))
        self.assertEqual(entry.value_delta, Decimal("-500.00"))

    def test_record_capital_gain_zero_quantity_delta(self):
        op = self._make_operation_with_item(
            CapitalGainOperation, OperationType.CAPITAL_GAIN, self.system, self.project
        )
        ProductLedgerEntry.record(op)
        entry = ProductLedgerEntry.objects.get(invoice_item=op.items.first())
        self.assertEqual(entry.entry_type, ProductLedgerEntry.EntryType.CAPITAL_GAIN)
        self.assertEqual(entry.quantity_delta, Decimal("0.00"))
        self.assertEqual(entry.value_delta, Decimal("500.00"))

    def test_record_capital_loss_zero_quantity_delta(self):
        op = self._make_operation_with_item(
            CapitalLossOperation, OperationType.CAPITAL_LOSS, self.project, self.system
        )
        ProductLedgerEntry.record(op)
        entry = ProductLedgerEntry.objects.get(invoice_item=op.items.first())
        self.assertEqual(entry.entry_type, ProductLedgerEntry.EntryType.CAPITAL_LOSS)
        self.assertEqual(entry.quantity_delta, Decimal("0.00"))
        self.assertEqual(entry.value_delta, Decimal("-500.00"))

    # --- idempotency and reversal ---

    def test_record_idempotent(self):
        op = self._make_operation_with_item(
            PurchaseOperation, OperationType.PURCHASE, self.project, self.vendor
        )
        created1, skipped1 = ProductLedgerEntry.record(op)
        created2, skipped2 = ProductLedgerEntry.record(op)
        self.assertEqual((created1, skipped1), (1, 0))
        self.assertEqual((created2, skipped2), (0, 1))
        self.assertEqual(ProductLedgerEntry.objects.count(), 1)

    def test_record_negate_creates_reversal_entry(self):
        op = self._make_operation_with_item(
            PurchaseOperation, OperationType.PURCHASE, self.project, self.vendor
        )
        ProductLedgerEntry.record(op)
        ProductLedgerEntry.record(op, negate=True)
        reversal = ProductLedgerEntry.objects.get(
            entry_type=ProductLedgerEntry.EntryType.REVERSAL
        )
        self.assertEqual(reversal.quantity_delta, Decimal("-5.00"))
        self.assertEqual(reversal.value_delta, Decimal("-500.00"))

    def test_record_unsupported_type_returns_zero(self):
        mock_op = MagicMock()
        mock_op.operation_type = OperationType.EXPENSE
        created, skipped = ProductLedgerEntry.record(mock_op)
        self.assertEqual((created, skipped), (0, 0))

    # --- state_as_of() ---

    def test_state_as_of_returns_zeros_when_no_entries(self):
        state = ProductLedgerEntry.state_as_of(self.product, date.today())
        self.assertEqual(state["quantity"], Decimal("0.00"))
        self.assertEqual(state["value"], Decimal("0.00"))

    def test_state_as_of_sums_entries(self):
        # state_as_of() only counts MOVEMENT_TYPES entries, so create a
        # PURCHASE_MOVEMENT ledger row directly.
        ProductLedgerEntry.objects.create(
            product=self.product,
            entry_type=ProductLedgerEntry.EntryType.PURCHASE_MOVEMENT,
            date=date.today(),
            quantity_delta=Decimal("10.00"),
            value_delta=Decimal("500.00"),
            idempotency_key="state_sums_movement_test",
        )
        state = ProductLedgerEntry.state_as_of(self.product, date.today())
        self.assertEqual(state["quantity"], Decimal("10.00"))
        self.assertEqual(state["value"], Decimal("500.00"))

    # --- portfolio_as_of() ---

    def test_record_negate_idempotent(self):
        """Calling record(negate=True) twice is idempotent — second call is skipped."""
        op = self._make_operation_with_item(
            PurchaseOperation, OperationType.PURCHASE, self.project, self.vendor
        )
        ProductLedgerEntry.record(op)
        created1, skipped1 = ProductLedgerEntry.record(op, negate=True)
        created2, skipped2 = ProductLedgerEntry.record(op, negate=True)
        self.assertEqual((created1, skipped1), (1, 0))
        self.assertEqual((created2, skipped2), (0, 1))
        self.assertEqual(
            ProductLedgerEntry.objects.filter(
                entry_type=ProductLedgerEntry.EntryType.REVERSAL
            ).count(),
            1,
        )

    # --- state_as_of() ---

    def test_state_as_of_excludes_entries_after_date(self):
        """Entries dated after as_of must not be included in the totals."""
        future = date.today() + timedelta(days=1)
        ProductLedgerEntry.objects.create(
            product=self.product,
            entry_type=ProductLedgerEntry.EntryType.PURCHASE_MOVEMENT,
            date=future,
            quantity_delta=Decimal("10.00"),
            value_delta=Decimal("1000.00"),
            idempotency_key="future_entry_test",
        )
        state = ProductLedgerEntry.state_as_of(self.product, date.today())
        self.assertEqual(state["quantity"], Decimal("0.00"))
        self.assertEqual(state["value"], Decimal("0.00"))

    def test_portfolio_as_of_excludes_zero_quantity_products(self):
        # portfolio_as_of() only counts MOVEMENT_TYPES entries. Give product2 a
        # net +3 (included) and self.product a net 0 (+5 purchase, -5 sale,
        # excluded).
        template2 = make_product_template("Sheep")
        template2.entities.add(self.project)
        product2 = make_product(template2, Decimal("80.00"), 3)
        ProductLedgerEntry.objects.create(
            product=product2,
            entry_type=ProductLedgerEntry.EntryType.PURCHASE_MOVEMENT,
            date=date.today(),
            quantity_delta=Decimal("3.00"),
            value_delta=Decimal("240.00"),
            idempotency_key="portfolio_product2_in",
        )
        ProductLedgerEntry.objects.create(
            product=self.product,
            entry_type=ProductLedgerEntry.EntryType.PURCHASE_MOVEMENT,
            date=date.today(),
            quantity_delta=Decimal("5.00"),
            value_delta=Decimal("500.00"),
            idempotency_key="portfolio_product1_in",
        )
        ProductLedgerEntry.objects.create(
            product=self.product,
            entry_type=ProductLedgerEntry.EntryType.SALE_MOVEMENT,
            date=date.today(),
            quantity_delta=Decimal("-5.00"),
            value_delta=Decimal("-500.00"),
            idempotency_key="portfolio_product1_out",
        )

        portfolio = list(ProductLedgerEntry.portfolio_as_of(self.project, date.today()))
        product_ids = {row["product_id"] for row in portfolio}
        self.assertNotIn(self.product.pk, product_ids)
        self.assertIn(product2.pk, product_ids)

    def test_portfolio_as_of_excludes_entries_after_date(self):
        """Entries dated after as_of must not appear in the portfolio."""
        future = date.today() + timedelta(days=1)
        ProductLedgerEntry.objects.create(
            product=self.product,
            entry_type=ProductLedgerEntry.EntryType.PURCHASE_MOVEMENT,
            date=future,
            quantity_delta=Decimal("5.00"),
            value_delta=Decimal("500.00"),
            idempotency_key="future_portfolio_test",
        )
        portfolio = list(ProductLedgerEntry.portfolio_as_of(self.project, date.today()))
        product_ids = {row["product_id"] for row in portfolio}
        self.assertNotIn(self.product.pk, product_ids)

    def test_available_products_and_value_after_death_consumption_sale(self):
        """Available stock must be distinguished from fully SOLD / DEAD /
        CONSUMED stock, and inventory value must reflect only what remains.

        Four products: one fully dead, one fully consumed, one fully sold, and
        one still on hand. Only the on-hand product appears in the portfolio
        and in the inventory value (fully written-off stock nets to zero).
        """
        template2 = make_product_template("Sheep")
        template2.entities.add(self.project)
        feed = ProductTemplate.objects.create(
            name="Feed Mix",
            nature=ProductTemplate.Nature.FEED,
            sub_category="Feed",
            default_unit="Kg",
        )
        feed.entities.add(self.project)

        dead = make_product(self.template, Decimal("100.00"), 10, entity=self.project)
        consumed = make_product(feed, Decimal("200.00"), 5, entity=self.project)
        sold = make_product(template2, Decimal("50.00"), 3, entity=self.project)
        available = make_product(template2, Decimal("25.00"), 7, entity=self.project)

        E = ProductLedgerEntry.EntryType
        rows = [
            (dead, E.PURCHASE_MOVEMENT, Decimal("10.00"), Decimal("1000.00")),
            (dead, E.DEATH_MOVEMENT, Decimal("-10.00"), Decimal("-1000.00")),
            (consumed, E.PURCHASE_MOVEMENT, Decimal("5.00"), Decimal("1000.00")),
            (consumed, E.CONSUMPTION_MOVEMENT, Decimal("-5.00"), Decimal("-1000.00")),
            (sold, E.PURCHASE_MOVEMENT, Decimal("3.00"), Decimal("150.00")),
            (sold, E.SALE_MOVEMENT, Decimal("-3.00"), Decimal("-150.00")),
            (available, E.PURCHASE_MOVEMENT, Decimal("7.00"), Decimal("175.00")),
        ]
        for i, (product, entry_type, qty, val) in enumerate(rows):
            ProductLedgerEntry.objects.create(
                product=product,
                entry_type=entry_type,
                date=date.today(),
                quantity_delta=qty,
                value_delta=val,
                idempotency_key=f"available_state_{i}",
            )

        portfolio = list(ProductLedgerEntry.portfolio_as_of(self.project, date.today()))
        product_ids = {row["product_id"] for row in portfolio}
        self.assertIn(available.pk, product_ids)
        self.assertNotIn(dead.pk, product_ids)
        self.assertNotIn(consumed.pk, product_ids)
        self.assertNotIn(sold.pk, product_ids)
        # Only the still-available product is returned, with its remaining value.
        self.assertEqual(len(portfolio), 1)
        self.assertEqual(portfolio[0]["quantity"], Decimal("7.00"))
        self.assertEqual(portfolio[0]["value"], Decimal("175.00"))

        # Inventory value = remaining on-hand stock only (written-off stock nets to 0).
        self.assertEqual(
            ProductLedgerEntry.inventory_value_at(self.project, date.today()),
            Decimal("175.00"),
        )
