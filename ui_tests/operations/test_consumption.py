"""UI happy-path tests for op_19 Consumption (docs/specs/operations/op_19_consumption.md).

Consumption is a stock event: it creates **no** transactions, auto-creates an
outbound movement line, and marks the consumed FEED/MEDICINE product CONSUMED
once fully written off. Happy path per the repo guidance: **create -> verify ->
reverse**.

Prerequisites (dependency chain):
- an ACTIVE Project,
- an ACTIVE consumable FEED/MEDICINE product owned by the project (purchased +
  received via the canonical ``make_moved_product`` fixture).
"""
from decimal import Decimal

from apps.app_inventory.models import Product, ProductTemplate
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import ConsumptionOperation

from ui_tests.base import UiTestCase
from ui_tests.operations.helpers import make_moved_product, make_product_template, make_vendor


class ConsumptionUiTests(UiTestCase):
    """op_19 Consumption full happy path (feed a consumable batch)."""

    def _ready_feed(self):
        """An ACTIVE consumable FEED batch owned by the project."""
        feed = make_product_template(
            self.project,
            name="Feed Mix",
            nature=ProductTemplate.Nature.FEED,
            default_unit="Kg",
            minimum_quantity=Decimal("1.00"),
            sub_category="Feed",
            can_be_consumed=True,
        )
        vendor = make_vendor(self.project, name="Feed Vendor")
        product = make_moved_product(
            self.project, feed, Decimal("50"), Decimal("2.00"), self.officer,
            vendor=vendor,
        )
        return product

    def _latest_consumption(self) -> ConsumptionOperation:
        from django.db.models import Q

        from apps.app_operation.models import Operation

        return Operation.objects.filter(
            Q(source=self.project) | Q(destination=self.project),
            operation_type=OperationType.CONSUMPTION,
        ).order_by("-created_at").cast()[0]  # type: ignore[attr-defined]

    def _create_consumption(self, product, qty=Decimal("50"), price=Decimal("2.00")):
        self.login_as_officer()
        self.goto("operation_create_view", self.project.pk, "consumption")
        # Formset row 0: select the existing FEED batch + qty/price.
        self.select("items-0-selected_product", product.pk)
        self.fill_amount(qty, "items-0-quantity")
        self.fill_amount(price, "items-0-unit_price")
        self.click_submit()
        self.wait_for_url_contains("detail")
        return self._latest_consumption()

    def test_happy_path_create_and_reverse(self):
        """SC: the consumption records the operation with an auto outbound movement
        line, marks the batch CONSUMED and leaves the fund untouched. SR:
        reversing it restores the batch to ACTIVE."""
        product = self._ready_feed()
        op = self._create_consumption(product)

        # ── create effects (SC) ────────────────────────────────────────
        self.assert_flash_contains("recorded successfully")
        self.assert_visible_text("Consumption")
        self.assert_visible_text("100.00")          # operation total (50 x 2.00)
        self.assert_visible_text("Inventory Movement Status")

        op.refresh_from_db()
        self.assertEqual(op.get_all_transactions().count(), 0, "consumption has no txs")
        self.assertEqual(op.items.count(), 1)  # type: ignore[attr-defined]
        self.assertEqual(op.movement_lines.count(), 1)  # type: ignore[attr-defined]

        # The batch is fully consumed.
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.CONSUMED)

        # Consumption is non-cash — the project fund never moved.
        self.assert_fund_balance(self.project, Decimal("5000.00"))

        # ── reverse effects (SR) ───────────────────────────────────────
        self.reverse_operation(op, reason="UI consumption data entry error")
        self.assert_visible_text("Operation Voided (Reversed)")

        op.refresh_from_db()
        self.assertIsNotNone(op.reversed_by)
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.ACTIVE)
