"""UI clause tests for the one-shot operations (no standalone pay/repay).

Covers op_2 Cash Withdrawal, op_3 Project Funding, op_4 Project Refund,
op_7 Internal Transfer and op_15 Correction Credit/Debit from their specs under
docs/specs/operations/. Each test opens a real browser, performs setup, executes
exactly one spec clause, and asserts the visible response.
"""
from datetime import date
from decimal import Decimal

from django.db.models import Q

from apps.app_entity.models import Entity, EntityType, StakeholderRole
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import ProjectFundingOperation

from ui_tests.base import (
    UiTestCase,
    make_person,
    make_project,
    make_stakeholder,
    inject_person_fund,
    inject_project_fund,
)


def make_internal_person(name):
    """A real internal Person (is_internal=True) — required for Internal Transfer."""
    return Entity.create(EntityType.PERSON, name=name, is_internal=True)


def make_shareholder(name):
    """A Person flagged is_shareholder — required by the funding/refund txs."""
    return Entity.create(EntityType.PERSON, name=name, is_shareholder=True)


def _fund(self, entity, amount):
    if entity.entity_type == "project":
        inject_project_fund(self.system, entity, amount, self.officer)
    else:
        inject_person_fund(self.world, entity, amount, self.officer)


class OneShotOpClauseMixin:
    """Shared clause tests for a one-shot operation.

    A plain mixin (NOT a TestCase subclass) so the test runner never discovers it.
    Concrete classes inherit from it plus ``UiTestCase``:
    ``class CashWithdrawalUiTests(OneShotOpClauseMixin, UiTestCase)``.

    Subclasses configure:
      op_type            — URL slug, e.g. "cash-withdrawal"
      primary_name       — name of the URL entity
      secondary_factory  — optional callable returning the entity to pick
      fund_primary       — optional amount to seed into the URL entity
      fund_secondary     — optional amount to seed into the picked entity
    """

    op_type = None
    primary_name = "One Shot Entity"
    secondary_factory = None
    fund_primary = None
    fund_secondary = None

    # -- setup -------------------------------------------------------------

    def _primary(self):
        return make_person(self.primary_name)

    def _secondary(self):
        return self.secondary_factory() if self.secondary_factory else None

    def _extra_setup(self, primary, secondary):
        pass

    def _ready_primary(self):
        primary = self._primary()
        if self.fund_primary:
            _fund(self, primary, self.fund_primary)
        return primary

    def _ready_secondary(self):
        secondary = self._secondary()
        if secondary is not None and self.fund_secondary:
            _fund(self, secondary, self.fund_secondary)
        return secondary

    def _latest_op(self, entity):
        from apps.app_operation.models import Operation

        return (
            Operation.objects.filter(Q(source=entity) | Q(destination=entity))
            .latest("created_at")
        )

    def _make_created(self, amount=Decimal("200.00")):
        primary = self._ready_primary()
        secondary = self._ready_secondary()
        self._extra_setup(primary, secondary)
        self.login_as_officer()
        self.create_one_shot(self.op_type, primary, amount, secondary=secondary)
        return primary, self._latest_op(primary)

    # -- clause tests -------------------------------------------------------

    def test_sc_create_success(self):
        """SC effect: the create flow records the operation and the detail shows
        the total."""
        primary, op = self._make_created(Decimal("300.00"))
        self.assert_flash_contains("recorded successfully")
        self.assert_visible_text("300.00")

    def test_vc_amount_positive(self):
        """VC: a zero amount is rejected with the spec's error."""
        primary = self._ready_primary()
        secondary = self._ready_secondary()
        self._extra_setup(primary, secondary)
        self.login_as_officer()
        self.goto("operation_create_view", primary.pk, self.op_type)
        if secondary is not None:
            self.select_secondary_entity(secondary)
        self.disable_html5_validation()
        self.fill_amount("0")
        self.fill("description", "zero amount UI test")
        self.click_submit()
        self.assert_visible_text("Amount should be positive")

    def test_vr5_reason_required(self):
        """VR5: reversing with an empty reason shows the error and stays put."""
        primary, op = self._make_created()
        self.goto("operation_reverse_view", op.pk)
        self.disable_html5_validation()
        self.click_submit()
        self.assert_flash_contains("A reason for reversal is required.")
        self.assertTrue(
            "reverse" in self.driver.current_url,
            f"expected to stay on the reverse form, got {self.driver.current_url}",
        )

    def test_sr_reverse_alert(self):
        """SR: a successful reversal marks the operation voided on the detail page."""
        primary, op = self._make_created()
        self.reverse_operation(op, reason="UI test data entry error")
        self.assert_visible_text("Operation Voided (Reversed)")


class CashWithdrawalUiTests(OneShotOpClauseMixin, UiTestCase):
    """op_2 Cash Withdrawal: person -> world, one-shot."""
    op_type = "cash-withdrawal"
    primary_name = "Withdrawal Person"
    fund_primary = Decimal("500.00")


class ProjectFundingUiTests(OneShotOpClauseMixin, UiTestCase):
    """op_3 Project Funding: person -> project (post picker), one-shot.

    The picker (get_related_entities) only lists projects where the person is an
    active shareholder, so the relation is created in setup.
    """
    op_type = "project-funding"
    primary_name = "Funding Person"
    fund_primary = Decimal("500.00")
    secondary_factory = staticmethod(lambda: make_project("Funding Target Project"))

    def _primary(self):
        return make_shareholder(self.primary_name)

    def _extra_setup(self, primary, secondary):
        make_stakeholder(
            secondary, primary, role=StakeholderRole.SHAREHOLDER, active=True
        )


class ProjectRefundUiTests(OneShotOpClauseMixin, UiTestCase):
    """op_4 Project Refund: project (post picker) -> person, one-shot.

    The destination person must be an active shareholder who has previously
    funded the project, so the refund cap (amount the shareholder funded) is met.
    """
    op_type = "project-refunding"
    primary_name = "Refund Shareholder"
    fund_secondary = Decimal("1000.00")
    secondary_factory = staticmethod(lambda: make_project("Refund Source Project"))

    def _primary(self):
        return make_shareholder(self.primary_name)

    def _extra_setup(self, primary, secondary):
        # Shareholder relation must exist before the funding op (its clean checks it).
        make_stakeholder(
            secondary, primary, role=StakeholderRole.SHAREHOLDER, active=True
        )
        # Person funds the project first (recorded funding + project balance).
        ProjectFundingOperation(
            source=primary,
            destination=secondary,
            amount=Decimal("1000.00"),
            operation_type=OperationType.PROJECT_FUNDING,
            date=date.today(),
            description="seed shareholder funding",
            officer=self.officer,
        ).save()


class InternalTransferUiTests(OneShotOpClauseMixin, UiTestCase):
    """op_7 Internal Transfer: internal entity -> internal entity (post picker)."""
    op_type = "internal-transfer"
    primary_name = "Transfer Source Person"
    fund_primary = Decimal("800.00")
    secondary_factory = staticmethod(lambda: make_internal_person("Transfer Target Person"))

    def _primary(self):
        return make_internal_person(self.primary_name)


class CorrectionCreditUiTests(OneShotOpClauseMixin, UiTestCase):
    """op_15 Correction Credit: system -> project, one-shot (no picker, no funds)."""
    op_type = "correction-credit"
    primary_name = "Credit Project"

    def _primary(self):
        return make_project(self.primary_name)


class CorrectionDebitUiTests(OneShotOpClauseMixin, UiTestCase):
    """op_15 Correction Debit: project -> system, one-shot (project must have funds)."""
    op_type = "correction-debit"
    primary_name = "Debit Project"
    fund_primary = Decimal("400.00")

    def _primary(self):
        return make_project(self.primary_name)
