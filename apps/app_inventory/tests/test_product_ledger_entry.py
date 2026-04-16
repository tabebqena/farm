from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from django.test import TestCase

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import ProductLedgerEntry
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

    # --- record() — all six operation types ---

    def test_record_purchase(self):
        op = self._make_operation_with_item(
            PurchaseOperation, OperationType.PURCHASE, self.project, self.vendor
        )
        created, skipped = ProductLedgerEntry.record(op)
        self.assertEqual((created, skipped), (1, 0))
        entry = ProductLedgerEntry.objects.get(product=self.product)
        self.assertEqual(entry.entry_type, ProductLedgerEntry.EntryType.PURCHASE)
        self.assertEqual(entry.quantity_delta, Decimal("5.00"))
        self.assertEqual(entry.value_delta, Decimal("500.00"))

    def test_record_sale(self):
        op = self._make_operation_with_item(
            SaleOperation, OperationType.SALE, self.client, self.project
        )
        ProductLedgerEntry.record(op)
        entry = ProductLedgerEntry.objects.get(product=self.product)
        self.assertEqual(entry.entry_type, ProductLedgerEntry.EntryType.SALE)
        self.assertEqual(entry.quantity_delta, Decimal("-5.00"))
        self.assertEqual(entry.value_delta, Decimal("-500.00"))

    def test_record_birth(self):
        op = self._make_operation_with_item(
            BirthOperation, OperationType.BIRTH, self.system, self.project
        )
        ProductLedgerEntry.record(op)
        entry = ProductLedgerEntry.objects.get(product=self.product)
        self.assertEqual(entry.entry_type, ProductLedgerEntry.EntryType.BIRTH)
        self.assertEqual(entry.quantity_delta, Decimal("5.00"))
        self.assertEqual(entry.value_delta, Decimal("500.00"))

    def test_record_death(self):
        op = self._make_operation_with_item(
            DeathOperation, OperationType.DEATH, self.project, self.system
        )
        ProductLedgerEntry.record(op)
        entry = ProductLedgerEntry.objects.get(product=self.product)
        self.assertEqual(entry.entry_type, ProductLedgerEntry.EntryType.DEATH)
        self.assertEqual(entry.quantity_delta, Decimal("-5.00"))
        self.assertEqual(entry.value_delta, Decimal("-500.00"))

    def test_record_capital_gain_zero_quantity_delta(self):
        op = self._make_operation_with_item(
            CapitalGainOperation, OperationType.CAPITAL_GAIN, self.system, self.project
        )
        ProductLedgerEntry.record(op)
        entry = ProductLedgerEntry.objects.get(product=self.product)
        self.assertEqual(entry.entry_type, ProductLedgerEntry.EntryType.CAPITAL_GAIN)
        self.assertEqual(entry.quantity_delta, Decimal("0.00"))
        self.assertEqual(entry.value_delta, Decimal("500.00"))

    def test_record_capital_loss_zero_quantity_delta(self):
        op = self._make_operation_with_item(
            CapitalLossOperation, OperationType.CAPITAL_LOSS, self.project, self.system
        )
        ProductLedgerEntry.record(op)
        entry = ProductLedgerEntry.objects.get(product=self.product)
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
        op = self._make_operation_with_item(
            PurchaseOperation,
            OperationType.PURCHASE,
            self.project,
            self.vendor,
            qty=Decimal("10.00"),
            price=Decimal("50.00"),
        )
        ProductLedgerEntry.record(op)
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
            entry_type=ProductLedgerEntry.EntryType.PURCHASE,
            date=future,
            quantity_delta=Decimal("10.00"),
            value_delta=Decimal("1000.00"),
            idempotency_key="future_entry_test",
        )
        state = ProductLedgerEntry.state_as_of(self.product, date.today())
        self.assertEqual(state["quantity"], Decimal("0.00"))
        self.assertEqual(state["value"], Decimal("0.00"))

    def test_portfolio_as_of_excludes_zero_quantity_products(self):
        # Purchase 5 units of self.product
        purchase_op = self._make_operation_with_item(
            PurchaseOperation,
            OperationType.PURCHASE,
            self.project,
            self.vendor,
            qty=Decimal("5.00"),
            price=Decimal("100.00"),
        )
        ProductLedgerEntry.record(purchase_op)

        # A second template/product still in stock
        template2 = make_product_template("Sheep")
        template2.entities.add(self.project)
        product2 = make_product(template2, Decimal("80.00"), 3)
        op2 = make_operation(
            self.project,
            self.vendor,
            self.officer,
            PurchaseOperation,
            OperationType.PURCHASE,
        )
        item2 = make_invoice_item(op2, template2, Decimal("3.00"), Decimal("80.00"))
        product2.invoice_items.add(item2)
        ProductLedgerEntry.record(op2)

        # Sell all 5 units of self.product → net quantity = 0
        sell_op = self._make_operation_with_item(
            SaleOperation,
            OperationType.SALE,
            self.client,
            self.project,
            qty=Decimal("5.00"),
            price=Decimal("100.00"),
        )
        ProductLedgerEntry.record(sell_op)

        portfolio = list(ProductLedgerEntry.portfolio_as_of(self.project, date.today()))
        product_ids = {row["product_id"] for row in portfolio}
        self.assertNotIn(self.product.pk, product_ids)
        self.assertIn(product2.pk, product_ids)

    def test_portfolio_as_of_excludes_entries_after_date(self):
        """Entries dated after as_of must not appear in the portfolio."""
        future = date.today() + timedelta(days=1)
        ProductLedgerEntry.objects.create(
            product=self.product,
            entry_type=ProductLedgerEntry.EntryType.PURCHASE,
            date=future,
            quantity_delta=Decimal("5.00"),
            value_delta=Decimal("500.00"),
            idempotency_key="future_portfolio_test",
        )
        portfolio = list(ProductLedgerEntry.portfolio_as_of(self.project, date.today()))
        product_ids = {row["product_id"] for row in portfolio}
        self.assertNotIn(self.product.pk, product_ids)
