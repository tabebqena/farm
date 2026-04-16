from datetime import date, timedelta
from decimal import Decimal

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


def _set_period_amount(period, amount):
    """Set amount on a period, bypassing immutability for test setup."""
    DjangoQuerySet.update(
        FinancialPeriod.all_objects.filter(pk=period.pk),
        amount=amount,
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

        # Close the auto-created period so amount can be set against it
        self.period = FinancialPeriod.objects.get(entity=self.project_entity)
        _force_close_period(self.period)
        # Open a new period so the entity remains active for new operations
        FinancialPeriod(entity=self.project_entity, start_date=TODAY).save()

    def _make_plan(self, amount):
        _set_period_amount(self.period, amount)
        return self.period

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


class PeriodAmountValidationTest(TestCase):
    def setUp(self):
        self.world = Entity.create(EntityType.WORLD)
        self.system = Entity.create(EntityType.SYSTEM)
        self.officer = _make_officer("officer_val")
        self.project_entity = _make_project_entity("Val Project")

        self.period = FinancialPeriod.objects.get(entity=self.project_entity)
        _force_close_period(self.period)
        FinancialPeriod(entity=self.project_entity, start_date=TODAY).save()

    def test_entity_must_be_a_project(self):
        person = Entity.create(EntityType.PERSON, name="Non-project person")
        non_project = person
        non_project_period = FinancialPeriod.objects.get(entity=non_project)
        _force_close_period(non_project_period)

        non_project_period.amount = Decimal("100.00")
        with self.assertRaises(ValidationError):
            non_project_period.save()

    def test_period_must_be_closed(self):
        open_period = FinancialPeriod.objects.get(
            entity=self.project_entity, end_date__isnull=True
        )
        open_period.amount = Decimal("100.00")
        with self.assertRaises(ValidationError):
            open_period.save()

    def test_amount_can_only_be_set_once(self):
        self.period.amount = Decimal("100.00")
        self.period.save()
        self.period.amount = Decimal("200.00")
        with self.assertRaises(ValidationError):
            self.period.save()


# ---------------------------------------------------------------------------
# FinancialPeriod — amount immutability
# ---------------------------------------------------------------------------


class PeriodAmountImmutabilityTest(TestCase):
    def setUp(self):
        self.system = Entity.create(EntityType.SYSTEM)
        self.officer = _make_officer("officer_imm")
        self.project_entity = _make_project_entity("Imm Project")

        self.period = FinancialPeriod.objects.get(entity=self.project_entity)
        _force_close_period(self.period)
        FinancialPeriod(entity=self.project_entity, start_date=TODAY).save()

        self.period.amount = Decimal("500.00")
        self.period.save()

    def test_amount_is_immutable(self):
        self.period.amount = Decimal("9999.00")
        with self.assertRaises(ValidationError):
            self.period.save()


# ---------------------------------------------------------------------------
# ShareholderAllocation
# ---------------------------------------------------------------------------


class ShareholderAllocationTest(TestCase):
    def setUp(self):
        self.system = Entity.create(EntityType.SYSTEM)
        self.officer = _make_officer("officer_alloc")
        self.project_entity = _make_project_entity("Alloc Project")
        self.shareholder = _make_shareholder_entity("Alloc Shareholder")

        self.period = FinancialPeriod.objects.get(entity=self.project_entity)
        _force_close_period(self.period)
        FinancialPeriod(entity=self.project_entity, start_date=TODAY).save()

        _set_period_amount(self.period, Decimal("1000.00"))

    def _make_allocation(self, percent, **kwargs):
        defaults = dict(
            period=self.period,
            shareholder=self.shareholder,
            percent=percent,
        )
        defaults.update(kwargs)
        alloc = ShareholderAllocation(**defaults)
        alloc.save()
        return alloc

    # --- instructional_amount ---

    def test_instructional_amount_is_percent_of_period_amount(self):
        alloc = self._make_allocation(Decimal("30.000"))
        self.assertEqual(alloc.instructional_amount, Decimal("300.00"))

    def test_instructional_amount_rounds_to_two_decimal_places(self):
        # 33.333% of 1000 = 333.33
        alloc = self._make_allocation(Decimal("33.333"))
        self.assertEqual(alloc.instructional_amount, Decimal("333.33"))

    # --- clean() validation ---

    def test_non_shareholder_entity_raises_validation_error(self):
        non_shareholder_person = Entity.create(
            EntityType.PERSON, name="Non Shareholder"
        )
        non_shareholder = non_shareholder_person  # is_shareholder=False by default
        alloc = ShareholderAllocation(
            period=self.period,
            shareholder=non_shareholder,
            percent=Decimal("50.000"),
        )
        with self.assertRaises(ValidationError):
            alloc.save()

    def test_negative_percent_raises_validation_error(self):
        alloc = ShareholderAllocation(
            period=self.period,
            shareholder=self.shareholder,
            percent=Decimal("-10.000"),
        )
        with self.assertRaises(ValidationError):
            alloc.save()

    def test_zero_percent_is_allowed(self):
        alloc = self._make_allocation(Decimal("0.000"))
        self.assertIsNotNone(alloc.pk)

    # --- unique constraint ---

    def test_unique_constraint_per_period_and_shareholder(self):
        self._make_allocation(Decimal("50.000"))
        duplicate = ShareholderAllocation(
            period=self.period,
            shareholder=self.shareholder,
            percent=Decimal("50.000"),
        )
        with self.assertRaises(Exception):  # IntegrityError or ValidationError
            duplicate.save()

    # --- multiple allocations ---

    def test_two_shareholders_can_have_allocations_in_same_period(self):
        second_shareholder = _make_shareholder_entity("Alloc Shareholder B")
        self._make_allocation(Decimal("60.000"))
        alloc2 = ShareholderAllocation(
            period=self.period,
            shareholder=second_shareholder,
            percent=Decimal("40.000"),
        )
        alloc2.save()
        self.assertIsNotNone(alloc2.pk)


# ---------------------------------------------------------------------------
# ProfitDistributionOperation — clean() validation
# ---------------------------------------------------------------------------


class ProfitDistributionOperationTest(TestCase):
    def setUp(self):
        self.world = Entity.create(EntityType.WORLD)
        self.system = Entity.create(EntityType.SYSTEM)
        self.officer = _make_officer("officer_pd")
        self.project_entity = _make_project_entity("PD Project")
        self.shareholder = _make_shareholder_entity("PD Shareholder")
        _register_shareholder(self.project_entity, self.shareholder)

        # Seed project balance
        _seed_capital_gain(
            self.system, self.project_entity, Decimal("2000.00"), self.officer
        )

        self.period = FinancialPeriod.objects.get(entity=self.project_entity)
        _force_close_period(self.period)
        FinancialPeriod(entity=self.project_entity, start_date=TODAY).save()

        _set_period_amount(self.period, Decimal("1000.00"))

    def _make_op(self, **kwargs):
        defaults = dict(
            source=self.project_entity,
            destination=self.shareholder,
            amount=Decimal("200.00"),
            operation_type=OperationType.PROFIT_DISTRIBUTION,
            date=TODAY,
            plan=self.period,
            officer=self.officer,
        )
        defaults.update(kwargs)
        return ProfitDistributionOperation(**defaults)

    # --- happy path ---

    def test_creates_successfully_within_plan_amount(self):
        op = self._make_op(amount=Decimal("500.00"))
        op.save()
        self.assertIsNotNone(op.pk)

    def test_is_fully_settled_after_creation(self):
        op = self._make_op(amount=Decimal("300.00"))
        op.save()
        self.assertTrue(op.is_fully_settled)

    # --- plan required ---

    def test_raises_without_plan(self):
        op = self._make_op(plan=None)
        with self.assertRaises(ValidationError):
            op.save()

    # --- plan must be a profit plan ---

    def test_raises_when_plan_is_a_loss(self):
        loss_project = _make_project_entity("Loss PD Project")
        _seed_capital_gain(self.system, loss_project, Decimal("1000.00"), self.officer)
        loss_period = FinancialPeriod.objects.get(entity=loss_project)
        _force_close_period(loss_period)
        FinancialPeriod(entity=loss_project, start_date=TODAY).save()
        _set_period_amount(loss_period, Decimal("-500.00"))

        shareholder = _make_shareholder_entity("PD Loss Shareholder")
        _register_shareholder(loss_project, shareholder)

        op = ProfitDistributionOperation(
            source=loss_project,
            destination=shareholder,
            amount=Decimal("100.00"),
            operation_type=OperationType.PROFIT_DISTRIBUTION,
            date=TODAY,
            plan=loss_period,
            officer=self.officer,
        )
        with self.assertRaises(ValidationError):
            op.save()

    def test_raises_when_plan_is_break_even(self):
        break_even_project = _make_project_entity("BreakEven PD Project")
        _seed_capital_gain(
            self.system, break_even_project, Decimal("1000.00"), self.officer
        )
        be_period = FinancialPeriod.objects.get(entity=break_even_project)
        _force_close_period(be_period)
        FinancialPeriod(entity=break_even_project, start_date=TODAY).save()
        _set_period_amount(be_period, Decimal("0.00"))

        shareholder = _make_shareholder_entity("PD BE Shareholder")
        _register_shareholder(break_even_project, shareholder)

        op = ProfitDistributionOperation(
            source=break_even_project,
            destination=shareholder,
            amount=Decimal("100.00"),
            operation_type=OperationType.PROFIT_DISTRIBUTION,
            date=TODAY,
            plan=be_period,
            officer=self.officer,
        )
        with self.assertRaises(ValidationError):
            op.save()

    # --- amount cap ---

    def test_raises_when_amount_exceeds_plan(self):
        op = self._make_op(amount=Decimal("1001.00"))  # period.amount = 1000
        with self.assertRaises(ValidationError):
            op.save()

    def test_raises_when_amount_exceeds_remaining_after_partial_distribution(self):
        # First distribution uses 700 of 1000
        self._make_op(amount=Decimal("700.00")).save()
        # Second distribution of 400 would exceed remaining (300)
        op = self._make_op(amount=Decimal("400.00"))
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_exactly_equal_to_remaining_is_allowed(self):
        self._make_op(amount=Decimal("600.00")).save()
        op = self._make_op(amount=Decimal("400.00"))  # exactly the remaining
        op.save()
        self.assertIsNotNone(op.pk)

    # --- destination validation ---

    def test_destination_must_be_shareholder(self):
        non_shareholder = Entity.create(EntityType.PERSON, name="Non-SH Person")
        op = self._make_op(destination=non_shareholder)
        with self.assertRaises(ValidationError):
            op.save()

    # --- reversed operations restore remaining ---

    def test_reversing_distribution_restores_remaining_distributable(self):
        op = self._make_op(amount=Decimal("500.00"))
        op.save()
        self.assertEqual(self.period.remaining_distributable, Decimal("500.00"))
        op.reverse(officer=self.officer)
        self.assertEqual(self.period.remaining_distributable, Decimal("1000.00"))


# ---------------------------------------------------------------------------
# LossCoverageOperation — clean() validation
# ---------------------------------------------------------------------------


class LossCoverageOperationTest(TestCase):
    def setUp(self):
        self.world = Entity.create(EntityType.WORLD)
        self.system = Entity.create(EntityType.SYSTEM)
        self.officer = _make_officer("officer_lc")
        self.project_entity = _make_project_entity("LC Project")
        self.shareholder = _make_shareholder_entity("LC Shareholder")
        _register_shareholder(self.project_entity, self.shareholder)

        # Seed shareholder balance so coverage payments succeed
        _seed_cash_injection(
            self.world, self.shareholder, Decimal("2000.00"), self.officer
        )

        self.period = FinancialPeriod.objects.get(entity=self.project_entity)
        _force_close_period(self.period)
        FinancialPeriod(entity=self.project_entity, start_date=TODAY).save()

        _set_period_amount(self.period, Decimal("-1000.00"))

    def _make_op(self, **kwargs):
        defaults = dict(
            source=self.shareholder,
            destination=self.project_entity,
            amount=Decimal("200.00"),
            operation_type=OperationType.LOSS_COVERAGE,
            date=TODAY,
            plan=self.period,
            officer=self.officer,
        )
        defaults.update(kwargs)
        return LossCoverageOperation(**defaults)

    # --- happy path ---

    def test_creates_successfully_within_plan_loss(self):
        op = self._make_op(amount=Decimal("500.00"))
        op.save()
        self.assertIsNotNone(op.pk)

    def test_is_fully_settled_after_creation(self):
        op = self._make_op(amount=Decimal("300.00"))
        op.save()
        self.assertTrue(op.is_fully_settled)

    # --- plan required ---

    def test_raises_without_plan(self):
        op = self._make_op(plan=None)
        with self.assertRaises(ValidationError):
            op.save()

    # --- plan must be a loss plan ---

    def test_raises_when_plan_is_a_profit(self):
        profit_project = _make_project_entity("Profit LC Project")
        _seed_capital_gain(
            self.system, profit_project, Decimal("1000.00"), self.officer
        )
        profit_period = FinancialPeriod.objects.get(entity=profit_project)
        _force_close_period(profit_period)
        FinancialPeriod(entity=profit_project, start_date=TODAY).save()
        _set_period_amount(profit_period, Decimal("500.00"))

        shareholder = _make_shareholder_entity("LC Profit Shareholder")
        _register_shareholder(profit_project, shareholder)
        _seed_cash_injection(self.world, shareholder, Decimal("1000.00"), self.officer)

        op = LossCoverageOperation(
            source=shareholder,
            destination=profit_project,
            amount=Decimal("100.00"),
            operation_type=OperationType.LOSS_COVERAGE,
            date=TODAY,
            plan=profit_period,
            officer=self.officer,
        )
        with self.assertRaises(ValidationError):
            op.save()

    # --- amount cap ---

    def test_raises_when_amount_exceeds_plan_loss(self):
        op = self._make_op(
            amount=Decimal("1001.00")
        )  # period.amount = -1000 → coverable = 1000
        with self.assertRaises(ValidationError):
            op.save()

    def test_raises_when_amount_exceeds_remaining_after_partial_coverage(self):
        self._make_op(amount=Decimal("700.00")).save()
        op = self._make_op(amount=Decimal("400.00"))  # remaining = 300
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_exactly_equal_to_remaining_is_allowed(self):
        self._make_op(amount=Decimal("600.00")).save()
        op = self._make_op(amount=Decimal("400.00"))  # exactly the remaining
        op.save()
        self.assertIsNotNone(op.pk)

    # --- reversed operations restore remaining ---

    def test_reversing_coverage_restores_remaining_coverable(self):
        op = self._make_op(amount=Decimal("500.00"))
        op.save()
        self.assertEqual(self.period.remaining_coverable, Decimal("500.00"))
        op.reverse(officer=self.officer)
        self.assertEqual(self.period.remaining_coverable, Decimal("1000.00"))
