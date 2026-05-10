from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import (
    InvoiceItem,
)
from apps.app_inventory.tests.general import (
    make_entity,
    make_invoice_item,
    make_operation,
    make_product_template,
    make_project_entity,
    make_user,
)

User = get_user_model()


class InvoiceItemTest(TestCase):
    def setUp(self):
        self.officer = make_user()
        self.vendor = make_entity(
            EntityType.PERSON, "Vendor", is_vendor=True, is_client=True
        )

        self.project = make_project_entity("Farm")
        Stakeholder.objects.create(
            parent=self.project,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )

        self.op = make_operation(self.project, self.vendor, self.officer)
        self.template = make_product_template()

    def test_total_price(self):
        item = make_invoice_item(self.op, self.template, Decimal("3"), Decimal("50.00"))
        self.assertEqual(item.total_price, Decimal("150.00"))

    def test_total_price_fractional_quantity(self):
        item = make_invoice_item(
            self.op, self.template, Decimal("2.5"), Decimal("40.00")
        )
        self.assertEqual(item.total_price, Decimal("100.00"))

    def test_clean_unit_price_negative_raises(self):
        item = InvoiceItem(
            operation=self.op,
            product_template=self.template,
            quantity=Decimal("1"),
            unit_price=Decimal("-10.00"),
        )
        with self.assertRaises(ValidationError):
            item.clean_unit_price()

    def test_clean_unit_price_zero_does_not_raise(self):
        # clean_unit_price only blocks negatives; zero unit price passes it
        item = InvoiceItem(
            operation=self.op,
            product_template=self.template,
            quantity=Decimal("1"),
            unit_price=Decimal("0.00"),
        )
        # Should not raise (zero is not < 0)
        item.clean_unit_price()

    def test_clean_quantity_zero_raises(self):
        # AmountCleanMixin checks _amount_name="quantity" > 0
        item = InvoiceItem(
            operation=self.op,
            product_template=self.template,
            quantity=Decimal("0"),
            unit_price=Decimal("10.00"),
        )
        with self.assertRaises(ValidationError):
            item.clean()

    def test_clean_quantity_negative_raises(self):
        item = InvoiceItem(
            operation=self.op,
            product_template=self.template,
            quantity=Decimal("-1"),
            unit_price=Decimal("10.00"),
        )
        with self.assertRaises(ValidationError):
            item.clean()

    def test_clean_valid_passes(self):
        item = InvoiceItem(
            operation=self.op,
            product_template=self.template,
            quantity=Decimal("2"),
            unit_price=Decimal("10.00"),
        )
        item.clean()  # should not raise

    def test_total_price_zero_unit_price(self):
        # total_price is a pure multiplication; zero unit_price is allowed
        item = InvoiceItem(
            operation=self.op,
            product_template=self.template,
            quantity=Decimal("5"),
            unit_price=Decimal("0.00"),
        )
        self.assertEqual(item.total_price, Decimal("0.00"))

    def test_clean_unit_price_positive_does_not_raise(self):
        item = InvoiceItem(
            operation=self.op,
            product_template=self.template,
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
        )
        item.clean_unit_price()  # should not raise

    def test_clean_does_not_enforce_unit_price(self):
        # clean() (AmountCleanMixin) only validates quantity; negative unit_price
        # must be caught by calling clean_unit_price() explicitly.
        item = InvoiceItem(
            operation=self.op,
            product_template=self.template,
            quantity=Decimal("1"),
            unit_price=Decimal("-5.00"),
        )
        item.clean()  # should not raise — unit_price is NOT checked here


class InvoiceItemAdjustmentPropertiesTest(TestCase):
    """Tests for adjustment-aware properties on InvoiceItem."""

    def setUp(self):
        self.officer = make_user()
        self.vendor = make_entity(
            EntityType.PERSON, "Vendor", is_vendor=True, is_client=True
        )
        self.project = make_project_entity("Farm")
        Stakeholder.objects.create(
            parent=self.project,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        self.op = make_operation(self.project, self.vendor, self.officer)
        self.template = make_product_template()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_item(self, qty: Decimal, price: Decimal) -> InvoiceItem:
        return make_invoice_item(self.op, self.template, qty, price)

    def _make_item_adj(self, operation=None, adj_type=None, officer=None):
        from apps.app_adjustment._item_type import InvoiceItemAdjustmentType
        from apps.app_adjustment.models import InvoiceItemAdjustment

        return InvoiceItemAdjustment.objects.create(
            operation=operation or self.op,
            type=adj_type or InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE,
            reason="test",
            date=date.today(),
            officer=officer or self.officer,
        )

    def _make_line(
        self, item_adj, invoice_item, new_quantity=None, new_unit_price=None
    ):
        from unittest import mock

        from apps.app_adjustment.models import InvoiceItemAdjustmentLine

        with mock.patch.object(
            InvoiceItemAdjustmentLine, "_sync_products", return_value=None
        ):
            return InvoiceItemAdjustmentLine.objects.create(
                adjustment=item_adj,
                invoice_item=invoice_item,
                new_quantity=new_quantity,
                new_unit_price=new_unit_price,
            )

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_no_adjustments(self):
        """No lines → all adjusted values equal originals; has_adjustments=False."""
        item = self._make_item(Decimal("5"), Decimal("100"))
        self.assertEqual(item.adjusted_quantity, Decimal("5"))
        self.assertEqual(item.adjusted_unit_price, Decimal("100"))
        self.assertEqual(item.adjusted_total_price, Decimal("500"))
        self.assertEqual(item.adjustment_quantity_delta, Decimal("0"))
        self.assertEqual(item.adjustment_value_delta, Decimal("0"))
        self.assertFalse(item.has_adjustments)

    def test_quantity_increase_adjustment(self):
        """new_quantity > original → adjusted_quantity reflects the new value."""
        item = self._make_item(Decimal("5"), Decimal("100"))
        adj = self._make_item_adj()
        self._make_line(adj, item, new_quantity=Decimal("8"))

        self.assertEqual(item.adjusted_quantity, Decimal("8"))
        self.assertEqual(item.adjustment_quantity_delta, Decimal("3"))
        # unit_price unchanged (no line touched it)
        self.assertEqual(item.adjusted_unit_price, Decimal("100"))
        self.assertEqual(item.adjusted_total_price, Decimal("800"))
        self.assertEqual(item.adjustment_value_delta, Decimal("300"))
        self.assertTrue(item.has_adjustments)

    def test_quantity_decrease_adjustment(self):
        """new_quantity < original → adjusted_quantity reflects the new value."""
        item = self._make_item(Decimal("5"), Decimal("100"))
        adj = self._make_item_adj()
        self._make_line(adj, item, new_quantity=Decimal("3"))

        self.assertEqual(item.adjusted_quantity, Decimal("3"))
        self.assertEqual(item.adjustment_quantity_delta, Decimal("-2"))
        self.assertEqual(item.adjusted_total_price, Decimal("300"))
        self.assertEqual(item.adjustment_value_delta, Decimal("-200"))

    def test_quantity_zero_adjustment(self):
        """new_quantity=0 (removal) → adjusted_quantity=0, total=0, value_delta = -original_total."""
        item = self._make_item(Decimal("5"), Decimal("100"))
        adj = self._make_item_adj()
        self._make_line(adj, item, new_quantity=Decimal("0"))

        self.assertEqual(item.adjusted_quantity, Decimal("0"))
        self.assertEqual(item.adjustment_quantity_delta, Decimal("-5"))
        self.assertEqual(item.adjusted_total_price, Decimal("0"))
        self.assertEqual(item.adjustment_value_delta, Decimal("-500"))

    def test_unit_price_change_only(self):
        """Only new_unit_price set → adjusted_unit_price updated; quantity unchanged."""
        item = self._make_item(Decimal("5"), Decimal("100"))
        adj = self._make_item_adj()
        self._make_line(adj, item, new_unit_price=Decimal("90"))

        self.assertEqual(item.adjusted_unit_price, Decimal("90"))
        self.assertEqual(item.adjusted_quantity, Decimal("5"))  # unchanged
        self.assertEqual(item.adjusted_total_price, Decimal("450"))  # 5 × 90
        self.assertEqual(item.adjustment_value_delta, Decimal("-50"))

    def test_both_quantity_and_price_change(self):
        """Both new_quantity and new_unit_price set in one line."""
        item = self._make_item(Decimal("5"), Decimal("100"))
        adj = self._make_item_adj()
        self._make_line(
            adj, item, new_quantity=Decimal("4"), new_unit_price=Decimal("80")
        )

        self.assertEqual(item.adjusted_quantity, Decimal("4"))
        self.assertEqual(item.adjusted_unit_price, Decimal("80"))
        self.assertEqual(item.adjusted_total_price, Decimal("320"))  # 4 × 80
        self.assertEqual(item.adjustment_quantity_delta, Decimal("-1"))
        self.assertEqual(item.adjustment_value_delta, Decimal("-180"))

    def test_reversed_adjustment_excluded(self):
        """Reversed adjustments are excluded from property calculations."""
        item = self._make_item(Decimal("5"), Decimal("100"))
        adj = self._make_item_adj()
        self._make_line(adj, item, new_quantity=Decimal("8"))

        # Confirm adjustments are seen before reversal
        self.assertTrue(item.has_adjustments)
        self.assertEqual(item.adjusted_quantity, Decimal("8"))

        # Reverse by creating a reversal record pointing to the original
        reversal = self._make_item_adj()
        reversal.reversal_of = adj
        reversal.save()

        # Refresh the item's cached relationships
        item.refresh_from_db()

        self.assertEqual(item.adjusted_quantity, Decimal("5"))  # back to original
        self.assertEqual(item.adjustment_quantity_delta, Decimal("0"))
        self.assertFalse(item.has_adjustments)

    def test_multiple_adjustments_accumulate(self):
        """Two lines affecting different fields: each field picks its own last value."""
        item = self._make_item(Decimal("5"), Decimal("100"))
        adj_a = self._make_item_adj()
        self._make_line(adj_a, item, new_quantity=Decimal("8"))

        adj_b = self._make_item_adj()
        self._make_line(adj_b, item, new_unit_price=Decimal("90"))

        # qty from line A, price from line B (higher pk)
        self.assertEqual(item.adjusted_quantity, Decimal("8"))
        self.assertEqual(item.adjusted_unit_price, Decimal("90"))
        # total = 8 × 90 = 720 (no interaction term error)
        self.assertEqual(item.adjusted_total_price, Decimal("720"))
        # deltas from original (5, 100)
        self.assertEqual(item.adjustment_quantity_delta, Decimal("3"))
        self.assertEqual(item.adjustment_value_delta, Decimal("220"))

    def test_last_value_wins_for_same_field(self):
        """When two lines change the same field, the last (highest pk) wins."""
        item = self._make_item(Decimal("5"), Decimal("100"))
        adj_a = self._make_item_adj()
        self._make_line(adj_a, item, new_quantity=Decimal("8"))

        adj_b = self._make_item_adj()
        self._make_line(adj_b, item, new_quantity=Decimal("6"))

        # Last value (pk B > pk A) should win, NOT sum of deltas
        self.assertEqual(item.adjusted_quantity, Decimal("6"))
        self.assertEqual(item.adjustment_quantity_delta, Decimal("1"))  # 6 - 5

    def test_has_adjustments_flag(self):
        """has_adjustments reflects presence of non-reversed lines."""
        item = self._make_item(Decimal("5"), Decimal("100"))
        self.assertFalse(item.has_adjustments)

        adj = self._make_item_adj()
        self._make_line(adj, item, new_quantity=Decimal("8"))
        self.assertTrue(item.has_adjustments)

        # After reversal, flag goes back to False
        reversal = self._make_item_adj()
        reversal.reversal_of = adj
        reversal.save()
        item.refresh_from_db()
        self.assertFalse(item.has_adjustments)
