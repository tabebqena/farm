"""UI happy-path tests for op_5/op_6 Capital Gain & Loss valuation.

The happy path (per repo guidance) is: evaluate a product -> reverse. Valuation is
value-only (no physical inventory movement).
"""
from datetime import date
from decimal import Decimal

from apps.app_inventory.models import Product, ProductTemplate
from apps.app_operation.models.operation_type import OperationType

from ui_tests.base import UiTestCase
from ui_tests.operations.helpers import make_product_template


class CapitalValuationUiTests(UiTestCase):
    """op_5 / op_6 via EvaluationCreateView (/<pk>/evaluate/<product_pk>/)."""

    def _make_product(self, unit_price=Decimal("100.00")):
        template = make_product_template(
            self.project,
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            default_unit="Head",
            sub_category="Cattle",
        )
        return Product.objects.create(
            product_template=template,
            entity=self.project,
            unit_price=unit_price,
            quantity=1,
        )

    def _latest_valuation(self, op_type):
        from apps.app_operation.models import Operation
        from django.db.models import Q

        return (
            Operation.objects.filter(
                Q(source=self.project) | Q(destination=self.project),
                operation_type=op_type,
            ).latest("created_at")
        )

    def _evaluate(self, product, new_unit_price):
        self.login_as_officer()
        self.goto("evaluation_create_view", self.project.pk, product.pk)
        self.fill_amount(f"{new_unit_price:.2f}", "new_unit_price")
        # The evaluation form requires a date (not auto-prefilled on submit).
        self.fill_date("date", date.today().isoformat())
        self.click_submit()
        self.wait_for_url_contains("detail")

    def test_capital_gain_happy_path(self):
        """Raising the unit price records a Capital Gain; reversal voids it."""
        product = self._make_product(unit_price=Decimal("100.00"))
        self._evaluate(product, Decimal("150.00"))
        op = self._latest_valuation(OperationType.CAPITAL_GAIN)
        self.assert_visible_text("Capital Gain")
        self.assert_visible_text("50.00")

        self.reverse_operation(op, reason="UI test valuation error")
        self.assert_visible_text("Operation Voided (Reversed)")

    def test_capital_loss_happy_path(self):
        """Lowering the unit price records a Capital Loss; reversal voids it."""
        product = self._make_product(unit_price=Decimal("100.00"))
        self._evaluate(product, Decimal("60.00"))
        op = self._latest_valuation(OperationType.CAPITAL_LOSS)
        self.assert_visible_text("Capital Loss")
        self.assert_visible_text("40.00")

        self.reverse_operation(op, reason="UI test valuation error")
        self.assert_visible_text("Operation Voided (Reversed)")
