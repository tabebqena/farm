"""UI tests for Cash Injection — docs/specs/operations/op_1_cash_injection.md.

Each test opens a real browser, does the setup, executes exactly one spec clause,
and asserts the visible response. One clause -> one test method.
"""
from decimal import Decimal

from ui_tests.base import UiTestCase, make_person


class CashInjectionCreateUiTests(UiTestCase):
    """op_1 create clauses (VC1, VC7) + SC6 balance effect."""

    def test_login_redirects_to_entity_list(self):
        """AUTH: the real login form logs the officer in and lands on the entity list."""
        self.login_as_officer()
        self.assert_on_route("entity_list")

    def test_vc1_source_is_world(self):
        """VC1: the create form locks the source to the World entity — it renders
        the World fund and offers no secondary-entity picker."""
        person = make_person("Shareholder Person")
        self.login_as_officer()
        self.goto("operation_create_view", person.pk, "cash-injection")
        self.assert_visible_text("New Cash Injection")
        self.assert_visible_text("Source Fund")
        self.assert_visible_text("World")
        # get_related_entities() is [] -> no <select name="secondary_entity">
        self.assert_no_element("select[name='secondary_entity']")

    def test_vc7_amount_positive(self):
        """VC7: a zero amount is rejected on the create form with the spec's error."""
        person = make_person("Shareholder Person")
        self.login_as_officer()
        self.goto("operation_create_view", person.pk, "cash-injection")
        self.disable_html5_validation()
        self.fill_amount("0")
        self.fill("description", "UI test zero amount")
        self.click_submit()
        self.assert_visible_text("Amount should be positive")

    def test_sc6_person_balance_increases(self):
        """SC6: creating an injection raises the person's visible fund balance and
        the detail page shows the total."""
        person = make_person("Ali Shareholder")
        self.login_as_officer()
        self.create_one_shot("cash-injection", person, Decimal("500.00"))
        self.assert_flash_contains("recorded successfully")
        self.assert_visible_text("Cash Injection")
        self.assert_visible_text("500.00")
        self.assert_fund_balance(person, Decimal("500.00"))


class CashInjectionReverseUiTests(UiTestCase):
    """op_1 reverse clauses (VR5) + reverse effects (SR8, SR9)."""

    def _make_created(self):
        person = make_person("Reversal Person")
        inject = None
        # create via the UI so the visible flow is exercised
        self.login_as_officer()
        self.create_one_shot("cash-injection", person, Decimal("200.00"))
        # find the created operation (the only cash injection for this person)
        from apps.app_operation.models import Operation
        from apps.app_operation.models.operation_type import OperationType

        inject = Operation.objects.filter(
            destination=person, operation_type=OperationType.CASH_INJECTION
        ).latest("created_at")
        return person, inject

    def test_vr5_reason_required(self):
        """VR5: reversing with an empty reason shows the error and stays on the form."""
        person, op = self._make_created()
        self.goto("operation_reverse_view", op.pk)
        self.disable_html5_validation()
        self.click_submit()  # empty reason
        self.assert_flash_contains("A reason for reversal is required.")
        self.assertTrue(
            "reverse" in self.driver.current_url,
            f"expected to stay on the reverse form, got {self.driver.current_url}",
        )

    def test_sr8_person_balance_restored(self):
        """SR8: after a successful reversal the person's visible balance is restored."""
        person, op = self._make_created()
        self.reverse_operation(op, reason="UI test data entry error")
        self.assert_visible_text("Operation Voided (Reversed)")
        self.assert_fund_balance(person, Decimal("0.00"))

    def test_sr9_settlement_cleared(self):
        """SR9: the reversal clears settlement — the list shows the Reversed badge,
        no longer Settled."""
        person, op = self._make_created()
        self.reverse_operation(op, reason="UI test duplicate")
        self.assert_visible_text("Operation Voided (Reversed)")
        self.goto("operation_list_view", person.pk)
        self.assert_visible_text("Reversed")
