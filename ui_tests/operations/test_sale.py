"""UI happy-path tests for op_14 Sale (docs/specs/operations/op_14_sale.md).

The sale is a multi-stage, invoice-based receivable operation. Its happy path
per the repo guidance is: **create (wizard) -> dispatch goods -> collect ->
reverse**.

Prerequisites (dependency chain the sale depends on, per the user's note):
- the Project must be ACTIVE and have a fund balance,
- the project must own physically-present stock: a successful PURCHASE with
  moved/received items (created here via the canonical ``make_moved_product``
  fixture, the same world the model suite asserts on),
- the project must have an ACTIVE client stakeholder (the buyer),
- the buyer's fund must cover the collection.

Each test drives the real browser through the wizard and asserts the visible
responses promised by the spec's success-effects sections (SC*, SP*, SR*).
"""
from decimal import Decimal

from apps.app_inventory.models import Product, ProductTemplate
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import SaleOperation

from ui_tests.base import UiTestCase, inject_person_fund
from ui_tests.operations.helpers import (
    make_client,
    make_moved_product,
    make_product_template,
    make_vendor,
)


class SaleUiTests(UiTestCase):
    """op_14 Sale full happy path via the session wizard."""

    def _ready_stock(self):
        """Purchase + receive 100 kg of corn -> ACTIVE on-hand stock for the sale."""
        vendor = make_vendor(self.project, name="Grain Vendor")
        template = make_product_template(
            self.project,
            name="Corn",
            nature=ProductTemplate.Nature.FEED,
            default_unit="Kg",
            minimum_quantity=Decimal("1.00"),
            sub_category="Feed",
        )
        return make_moved_product(
            self.project, template, Decimal("100"), Decimal("3.00"), self.officer,
            vendor=vendor,
        )

    def _ready_client(self):
        """An active client stakeholder of the project, with funds to collect from."""
        client = make_client(self.project, name="Big Buyer")
        inject_person_fund(self.world, client, Decimal("5000.00"), self.officer)
        return client

    def _latest_sale(self) -> SaleOperation:
        from django.db.models import Q

        from apps.app_operation.models import Operation

        return Operation.objects.filter(
            Q(source=self.project) | Q(destination=self.project),
            operation_type=OperationType.SALE,
        ).order_by("-created_at").cast()[0]  # type: ignore[attr-defined]

    def _run_sale_wizard(
        self,
        client,
        product,
        total=Decimal("500.00"),
        qty=Decimal("100"),
        price=Decimal("5.00"),
        collected=Decimal("200.00"),
    ):
        """Drive the whole sale wizard (steps 1-3 -> invoice -> item -> submit)."""
        self.login_as_officer()
        # Step 1 — client + description (date pre-filled with today).
        self.goto("sale_wizard_step1", self.project.pk)
        self.select("client", client.pk)
        self.fill("description", "UI sale")
        self.click_wizard_next()
        self.wait_for_url_contains("/2/")
        # Step 2 — declared invoice total.
        self.fill_amount(total, "total_amount")
        self.click_wizard_next()
        self.wait_for_url_contains("/3/")
        # Step 3 — optional initial collection.
        self.fill_amount(collected, "amount_paid")
        self.click_wizard_next()
        self.wait_for_url_contains("invoice")
        # Add the stock product to the invoice (full dispatch).
        self.goto_query("sale_add_item", self.project.pk, product_id=product.pk)
        self.fill_amount(qty, "quantity")
        self.fill_amount(price, "unit_price")
        self.click_submit("Add to Invoice")
        self.wait_for_url_contains("invoice")
        # Submit the invoice -> operation detail.
        self.click_submit("Submit Sale")
        self.wait_for_url_contains("detail")
        return self._latest_sale()

    def _reverse_sale_movement(self, op):
        """Reverse the auto SALE dispatch line (confirm page -> POST)."""
        line = op.movement_lines.first()  # type: ignore[attr-defined]
        self.goto("reverse_inventory_movement_line", line.pk)
        self.click_submit()
        self.wait_for_url_contains("detail")

    # ------------------------------------------------------------------
    # Happy path: create -> dispatch goods -> collect
    # ------------------------------------------------------------------

    def test_happy_path_create_dispatch_collect(self):
        """SC: the wizard sale records the receivable, dispatches the stock and
        marks the product SOLD; the collection raises the project fund."""
        product = self._ready_stock()
        client = self._ready_client()
        op = self._run_sale_wizard(client, product)

        # ── create effects (SC) ────────────────────────────────────────
        self.assert_flash_contains("recorded successfully")
        self.assert_visible_text("Sale")
        self.assert_visible_text("500.00")          # invoice total / total
        self.assert_visible_text("200.00")          # total collected
        self.assert_visible_text("300.00")          # remaining balance
        self.assert_visible_text("Invoice Items")
        self.assert_visible_text("Inventory Movement Status")
        self.assert_visible_text("100")             # delivered qty

        # The full dispatch leaves the product SOLD.
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.SOLD)

        # The initial collection raised the project fund by 200.
        self.assert_fund_balance(self.project, Decimal("5200.00"))

        # ORM: issuance + one collection tx; one item; one SALE movement line.
        op.refresh_from_db()
        self.assertEqual(op.get_all_transactions().count(), 2)
        self.assertEqual(op.items.count(), 1)  # type: ignore[attr-defined]
        self.assertEqual(op.movement_lines.count(), 1)  # type: ignore[attr-defined]
        self.assertEqual(  # type: ignore[attr-defined]
            op.amount_remaining_to_settle, Decimal("300.00")
        )

        # ── pay (SP — collection) ──────────────────────────────────────
        self.record_payment(op, Decimal("300.00"))
        self.assert_flash_contains("Payment")
        self.assert_visible_text("Fully Paid")
        self.assert_visible_text("300.00")          # total collected reaches 500
        self.assert_fund_balance(self.project, Decimal("5500.00"))

        op.refresh_from_db()
        self.assertEqual(op.amount_settled, Decimal("500.00"))  # type: ignore[attr-defined]
        self.assertEqual(  # type: ignore[attr-defined]
            op.amount_remaining_to_settle, Decimal("0.00")
        )

    # ------------------------------------------------------------------
    # Happy path: reverse (undo dispatch first, then the sale)
    # ------------------------------------------------------------------

    def test_happy_path_reverse(self):
        """SR: undoing the SALE movement restores the stock, then reversing the
        sale voids it and restores the product to ACTIVE."""
        product = self._ready_stock()
        client = self._ready_client()
        op = self._run_sale_wizard(
            client, product, collected=Decimal("0.00")
        )
        self.assert_fund_balance(self.project, Decimal("5000.00"))

        # A sale with a dispatched movement cannot be reversed until the
        # movement is undone first — do that through the UI confirm flow.
        self._reverse_sale_movement(op)
        self.assert_flash_contains("Movement line reversed successfully")
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.ACTIVE)

        self.reverse_operation(op, reason="UI sale data entry error")
        self.assert_visible_text("Operation Voided (Reversed)")

        op.refresh_from_db()
        self.assertIsNotNone(op.reversed_by)
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.ACTIVE)
