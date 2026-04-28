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
