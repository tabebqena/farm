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
