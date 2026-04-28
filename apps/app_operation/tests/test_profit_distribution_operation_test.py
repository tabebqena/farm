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
