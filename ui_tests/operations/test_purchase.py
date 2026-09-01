"""UI happy-path tests for op_13 Purchase (docs/specs/operations/op_13_purchase.md).

The purchase is a multi-stage, invoice-based payable operation. Its happy path
per the repo guidance is: **create (wizard) -> receive items -> pay -> reverse**.

Prerequisites (the world the sale/sale-chain tests also rely on):
- an active Project with a real fund balance,
- at least one active Vendor stakeholder of the project,
- a ProductTemplate assigned to the project.

Each test drives the real browser through the wizard and asserts the visible
responses promised by the spec's success-effects sections (SC*, SP*, SR*).
"""
from decimal import Decimal

from apps.app_inventory.models import InventoryMovementLine, Product, ProductTemplate
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import PurchaseOperation

from ui_tests.base import UiTestCase
from ui_tests.operations.helpers import make_product_template, make_vendor


class PurchaseUiTests(UiTestCase):
    """op_13 Purchase full happy path via the session wizard."""

    def _ready(self):
        """Active project with a vendor + a FEED template assigned to it."""
        vendor = make_vendor(self.project, name="Agri Supplies Ltd")
        template = make_product_template(
            self.project,
            name="Feed Mix",
            nature=ProductTemplate.Nature.FEED,
            default_unit="Kg",
            minimum_quantity=Decimal("1.00"),
            sub_category="Feed",
        )
        return vendor, template

    def _latest_purchase(self) -> PurchaseOperation:
        from django.db.models import Q

        from apps.app_operation.models import Operation

        # .cast() re-types each row to its proxy subclass (PurchaseOperation),
        # giving access to the settlement/invoice mixin surface at runtime.
        return Operation.objects.filter(  # type: ignore[attr-defined]
            Q(source=self.project) | Q(destination=self.project),
            operation_type=OperationType.PURCHASE,
        ).order_by("-created_at").cast()[0]

    def _run_wizard(
        self,
        vendor,
        template,
        total=Decimal("300.00"),
        qty=Decimal("100"),
        price=Decimal("3.00"),
        received_qty=Decimal("100"),
        paid=Decimal("100.00"),
    ):
        """Drive the whole purchase wizard (steps 1-3 -> invoice -> item -> submit)."""
        self.login_as_officer()
        # Step 1 — basic info (date is pre-filled with today, covered by the open period).
        self.goto("purchase_wizard_step1", self.project.pk)
        self.select("vendor", vendor.pk)
        self.fill("description", "UI purchase")
        self.click_wizard_next()
        self.wait_for_url_contains("/2/")
        # Step 2 — declared total.
        self.fill_amount(total, "total_amount")
        self.click_wizard_next()
        self.wait_for_url_contains("/3/")
        # Step 3 — optional initial payment.
        self.fill_amount(paid, "amount_paid")
        self.click_wizard_next()
        self.wait_for_url_contains("invoice")
        # Add the invoice item (commodity template — no tag required).
        self.goto_query(
            "purchase_add_item", self.project.pk, template_id=template.pk
        )
        self.fill_amount(qty, "quantity")
        self.fill_amount(price, "unit_price")
        self.fill_amount(received_qty, "received_qty")
        self.fill("description", "Feed Mix lot")
        self.click_submit("Add Item")
        self.wait_for_url_contains("invoice")
        # Submit the invoice -> operation detail.
        self.click_submit("Submit Purchase")
        self.wait_for_url_contains("detail")
        return self._latest_purchase()

    # ------------------------------------------------------------------
    # Happy path: create -> receive items -> pay
    # ------------------------------------------------------------------

    def test_happy_path_create_receive_pay(self):
        """SC: wizard create records the purchase with invoice + movement lines;
        the payment moves the project fund and lowers the remaining balance."""
        vendor, template = self._ready()
        op = self._run_wizard(
            vendor, template, total=Decimal("300.00"),
            qty=Decimal("100"), price=Decimal("3.00"),
            received_qty=Decimal("100"), paid=Decimal("100.00"),
        )

        # ── create effects (SC) ────────────────────────────────────────
        self.assert_flash_contains("recorded successfully")
        self.assert_visible_text("Purchase")
        self.assert_visible_text("300.00")          # invoice total / total
        self.assert_visible_text("100.00")          # total paid
        self.assert_visible_text("200.00")          # remaining balance
        self.assert_visible_text("Invoice Items")
        self.assert_visible_text("Inventory Movement Status")
        # The movement line is on the detail page: received qty 100, remaining 0.
        self.assert_visible_text("100")

        # Issuance is non-cash: only the initial payment moved the project fund.
        self.assert_fund_balance(self.project, Decimal("4900.00"))

        # ORM: issuance + one payment tx; one invoice item; one inbound line.
        op.refresh_from_db()
        self.assertEqual(
            op.get_all_transactions().count(), 2,
            "expected exactly one issuance + one payment transaction",
        )
        self.assertEqual(op.items.count(), 1)  # type: ignore[attr-defined]
        self.assertEqual(op.movement_lines.count(), 1)  # type: ignore[attr-defined]
        self.assertEqual(  # type: ignore[attr-defined]
            op.amount_remaining_to_settle, Decimal("200.00")
        )

        # The received product is physically present and ACTIVE.
        product = Product.objects.get(entity=self.project)
        self.assertEqual(product.status, Product.Status.ACTIVE)

        # ── pay (SP) ───────────────────────────────────────────────────
        self.record_payment(op, Decimal("50.00"))
        self.assert_flash_contains("Payment")
        self.assert_visible_text("150.00")          # total paid
        self.assert_visible_text("150.00")          # remaining balance
        self.assert_fund_balance(self.project, Decimal("4850.00"))

        op.refresh_from_db()
        self.assertEqual(op.amount_settled, Decimal("150.00"))  # type: ignore[attr-defined]
        self.assertEqual(  # type: ignore[attr-defined]
            op.amount_remaining_to_settle, Decimal("150.00")
        )

    # ------------------------------------------------------------------
    # Happy path: reverse a pure issuance (no payments / movements)
    # ------------------------------------------------------------------

    def test_happy_path_reverse(self):
        """SR: reversing a purchase that has no payments or movements voids it
        and restores the project's payables."""
        vendor, template = self._ready()
        op = self._run_wizard(
            vendor, template, total=Decimal("200.00"),
            qty=Decimal("50"), price=Decimal("4.00"),
            received_qty=Decimal("0"), paid=Decimal("0.00"),
        )
        # Creation was pure-issuance: no movements, no payments, fund untouched.
        self.assert_fund_balance(self.project, Decimal("5000.00"))
        op.refresh_from_db()
        self.assertEqual(op.movement_lines.count(), 0)  # type: ignore[attr-defined]
        self.assertEqual(op.get_all_transactions().count(), 1)

        self.reverse_operation(op, reason="UI purchase data entry error")
        self.assert_visible_text("Operation Voided (Reversed)")

        op.refresh_from_db()
        self.assertIsNotNone(op.reversed_by)
        # Reversal carries no explicit transactions of its own.
        self.assertEqual(  # type: ignore[attr-defined]
            op.reversed_by.get_all_transactions().count(), 0
        )
