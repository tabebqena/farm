from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import PropertyMock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import QuerySet as DjangoQuerySet
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.period import FinancialPeriod
from apps.app_operation.models.proxies import (
    CapitalGainOperation,
    CashInjectionOperation,
    LossCoverageOperation,
    ProfitDistributionOperation,
)
from apps.app_operation.models.share_allocation import ShareholderAllocation

User = get_user_model()

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)
LAST_MONTH = TODAY - timedelta(days=30)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_officer(username="officer_dp"):
    return User.objects.create_user(username=username, password="x", is_staff=True)


def _make_project_entity(name="Test Project"):
    return Entity.create(EntityType.PROJECT, name=name)


def _make_shareholder_entity(name="Shareholder A"):
    person = Entity.create(EntityType.PERSON, is_shareholder=True, name=name)
    return person


def _register_shareholder(project_entity, shareholder_entity):
    Stakeholder(
        parent=project_entity,
        target=shareholder_entity,
        role=StakeholderRole.SHAREHOLDER,
    ).save()


def _force_close_period(period):
    """
    Bypass SafeQuerySet to set end_date in the past so is_closed == True.
    Also backdates start_date so the period interval is valid.
    """
    DjangoQuerySet.update(
        FinancialPeriod.all_objects.filter(pk=period.pk),
        start_date=LAST_MONTH,
        end_date=YESTERDAY,
    )
    period.refresh_from_db()


def _seed_capital_gain(system, destination, amount, officer):
    CapitalGainOperation(
        source=system,
        destination=destination,
        amount=amount,
        operation_type=OperationType.CAPITAL_GAIN,
        date=TODAY,
        officer=officer,
    ).save()


def _seed_cash_injection(world, destination, amount, officer):
    CashInjectionOperation(
        source=world,
        destination=destination,
        amount=amount,
        operation_type=OperationType.CASH_INJECTION,
        date=TODAY,
        officer=officer,
    ).save()


# ---------------------------------------------------------------------------
# FinancialPeriod — P&L properties
# ---------------------------------------------------------------------------


class PeriodProfitLossPropertiesTest(TestCase):
    def setUp(self):
        self.world = Entity.create(EntityType.WORLD)
        self.system = Entity.create(EntityType.SYSTEM)
        self.officer = _make_officer("officer_props")
        self.project_entity = _make_project_entity("Props Project")
        self.shareholder = _make_shareholder_entity("Props Shareholder")
        _register_shareholder(self.project_entity, self.shareholder)

        # Seed project with enough balance for ProfitDistribution operations
        _seed_capital_gain(
            self.system, self.project_entity, Decimal("2000.00"), self.officer
        )
        # Seed shareholder for LossCoverage operations
        _seed_cash_injection(
            self.world, self.shareholder, Decimal("2000.00"), self.officer
        )

        # Close the auto-created period so amount can be calculated
        self.period = FinancialPeriod.objects.get(entity=self.project_entity)
        _force_close_period(self.period)
        # Open a new period so the entity remains active for new operations
        FinancialPeriod(entity=self.project_entity, start_date=TODAY).save()

    def _make_plan(self, amount):
        """Patch the period's amount property to return the given amount."""
        # Patch the amount property on the FinancialPeriod class
        patch.object(
            FinancialPeriod, 'amount', new_callable=PropertyMock, return_value=amount
        ).start()
        return self.period

    def tearDown(self):
        """Stop all patches."""
        patch.stopall()

    # --- is_profit / is_loss ---

    def test_is_profit_true_for_positive_amount(self):
        plan = self._make_plan(Decimal("500.00"))
        self.assertTrue(plan.is_profit)
        self.assertFalse(plan.is_loss)

    def test_is_loss_true_for_negative_amount(self):
        plan = self._make_plan(Decimal("-300.00"))
        self.assertTrue(plan.is_loss)
        self.assertFalse(plan.is_profit)

    def test_break_even_is_neither_profit_nor_loss(self):
        plan = self._make_plan(Decimal("0.00"))
        self.assertFalse(plan.is_profit)
        self.assertFalse(plan.is_loss)

    # --- distributed / remaining_distributable ---

    def test_distributed_zero_when_no_operations(self):
        plan = self._make_plan(Decimal("500.00"))
        self.assertEqual(plan.distributed, Decimal("0.00"))

    def test_remaining_distributable_equals_amount_when_nothing_distributed(self):
        plan = self._make_plan(Decimal("800.00"))
        self.assertEqual(plan.remaining_distributable, Decimal("800.00"))

    def test_remaining_distributable_zero_for_loss_plan(self):
        plan = self._make_plan(Decimal("-400.00"))
        self.assertEqual(plan.remaining_distributable, Decimal("0.00"))

    def test_distributed_increases_after_distribution_op(self):
        plan = self._make_plan(Decimal("600.00"))
        ProfitDistributionOperation(
            source=self.project_entity,
            destination=self.shareholder,
            amount=Decimal("200.00"),
            operation_type=OperationType.PROFIT_DISTRIBUTION,
            date=TODAY,
            plan=plan,
            officer=self.officer,
        ).save()
        self.assertEqual(plan.distributed, Decimal("200.00"))

    def test_remaining_distributable_decreases_after_distribution_op(self):
        plan = self._make_plan(Decimal("600.00"))
        ProfitDistributionOperation(
            source=self.project_entity,
            destination=self.shareholder,
            amount=Decimal("200.00"),
            operation_type=OperationType.PROFIT_DISTRIBUTION,
            date=TODAY,
            plan=plan,
            officer=self.officer,
        ).save()
        self.assertEqual(plan.remaining_distributable, Decimal("400.00"))

    def test_distributed_excludes_reversed_operations(self):
        plan = self._make_plan(Decimal("600.00"))
        op = ProfitDistributionOperation(
            source=self.project_entity,
            destination=self.shareholder,
            amount=Decimal("200.00"),
            operation_type=OperationType.PROFIT_DISTRIBUTION,
            date=TODAY,
            plan=plan,
            officer=self.officer,
        )
        op.save()
        op.reverse(officer=self.officer)
        # Reversed op (and its reversal) must not count towards distributed
        self.assertEqual(plan.distributed, Decimal("0.00"))

    # --- covered / remaining_coverable ---

    def test_covered_zero_when_no_operations(self):
        plan = self._make_plan(Decimal("-500.00"))
        self.assertEqual(plan.covered, Decimal("0.00"))

    def test_remaining_coverable_equals_abs_amount_when_nothing_covered(self):
        plan = self._make_plan(Decimal("-400.00"))
        self.assertEqual(plan.remaining_coverable, Decimal("400.00"))

    def test_remaining_coverable_zero_for_profit_plan(self):
        plan = self._make_plan(Decimal("300.00"))
        self.assertEqual(plan.remaining_coverable, Decimal("0.00"))

    def test_covered_increases_after_coverage_op(self):
        plan = self._make_plan(Decimal("-600.00"))
        LossCoverageOperation(
            source=self.shareholder,
            destination=self.project_entity,
            amount=Decimal("150.00"),
            operation_type=OperationType.LOSS_COVERAGE,
            date=TODAY,
            plan=plan,
            officer=self.officer,
        ).save()
        self.assertEqual(plan.covered, Decimal("150.00"))

    def test_remaining_coverable_decreases_after_coverage_op(self):
        plan = self._make_plan(Decimal("-600.00"))
        LossCoverageOperation(
            source=self.shareholder,
            destination=self.project_entity,
            amount=Decimal("150.00"),
            operation_type=OperationType.LOSS_COVERAGE,
            date=TODAY,
            plan=plan,
            officer=self.officer,
        ).save()
        self.assertEqual(plan.remaining_coverable, Decimal("450.00"))

    def test_covered_excludes_reversed_operations(self):
        plan = self._make_plan(Decimal("-600.00"))
        op = LossCoverageOperation(
            source=self.shareholder,
            destination=self.project_entity,
            amount=Decimal("200.00"),
            operation_type=OperationType.LOSS_COVERAGE,
            date=TODAY,
            plan=plan,
            officer=self.officer,
        )
        op.save()
        op.reverse(officer=self.officer)
        self.assertEqual(plan.covered, Decimal("0.00"))

    # --- allocations_balanced ---

    def test_allocations_balanced_true_when_sum_is_100(self):
        plan = self._make_plan(Decimal("1000.00"))
        ShareholderAllocation(
            period=plan, shareholder=self.shareholder, percent=Decimal("100.000")
        ).save()
        self.assertTrue(plan.allocations_balanced)

    def test_allocations_balanced_false_when_sum_not_100(self):
        plan = self._make_plan(Decimal("1000.00"))
        ShareholderAllocation(
            period=plan, shareholder=self.shareholder, percent=Decimal("60.000")
        ).save()
        self.assertFalse(plan.allocations_balanced)

    def test_allocations_balanced_false_when_no_allocations(self):
        plan = self._make_plan(Decimal("1000.00"))
        self.assertFalse(plan.allocations_balanced)


# ---------------------------------------------------------------------------
# FinancialPeriod — amount validation
# ---------------------------------------------------------------------------
