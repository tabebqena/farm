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
    CashInjectionOperation,
    LossCoverageOperation,
)
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
LAST_MONTH = TODAY - timedelta(days=30)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_officer(username):
    return User.objects.create_user(username=username, password="x", is_staff=True)


def _make_project_entity(name):

    return Entity.create(EntityType.PROJECT, name=name)


def _make_shareholder_entity(name):
    person = Entity.create(EntityType.PERSON, name=name)
    entity = person
    entity.is_shareholder = True
    entity.save()
    return entity


def _register_shareholder(project_entity, shareholder_entity):
    Stakeholder(
        parent=project_entity,
        target=shareholder_entity,
        role=StakeholderRole.SHAREHOLDER,
    ).save()


def _force_close_period(period):
    DjangoQuerySet.update(
        FinancialPeriod.all_objects.filter(pk=period.pk),
        start_date=LAST_MONTH,
        end_date=YESTERDAY,
    )
    period.refresh_from_db()


def _set_period_amount(period, amount):
    DjangoQuerySet.update(
        FinancialPeriod.all_objects.filter(pk=period.pk),
        amount=amount,
    )
    period.refresh_from_db()


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
# Create
# ---------------------------------------------------------------------------


class LossCoverageReversalTest(TestCase):
    def setUp(self):
        self.world = Entity.create(EntityType.WORLD)
        self.system = Entity.create(EntityType.SYSTEM)
        self.officer = _make_officer("officer_lc_rev")
        self.project_entity = _make_project_entity("LC Reversal Project")
        self.shareholder = _make_shareholder_entity("LC Reversal Shareholder")
        _register_shareholder(self.project_entity, self.shareholder)

        _seed_cash_injection(
            self.world, self.shareholder, Decimal("2000.00"), self.officer
        )

        self.period = FinancialPeriod.objects.get(entity=self.project_entity)
        _force_close_period(self.period)
        FinancialPeriod(entity=self.project_entity, start_date=TODAY).save()

        _set_period_amount(self.period, Decimal("-1000.00"))

        self.op = LossCoverageOperation(
            source=self.shareholder,
            destination=self.project_entity,
            amount=Decimal("500.00"),
            operation_type=OperationType.LOSS_COVERAGE,
            date=TODAY,
            plan=self.period,
            officer=self.officer,
        )
        self.op.save()

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_reverse_creates_reversal_operation(self):
        reversal = self.op.reverse(officer=self.officer)

        self.assertIsNotNone(reversal.pk)
        self.assertEqual(reversal.reversal_of, self.op)

    def test_reverse_marks_original_as_reversed(self):
        reversal = self.op.reverse(officer=self.officer)

        self.op.refresh_from_db()
        self.assertTrue(self.op.is_reversed)
        self.assertEqual(self.op.reversed_by, reversal)

    def test_reversal_is_reversal(self):
        reversal = self.op.reverse(officer=self.officer)

        self.assertTrue(reversal.is_reversal)
        self.assertFalse(reversal.is_reversed)

    def test_reverse_inherits_amount_source_destination(self):
        reversal = self.op.reverse(officer=self.officer)

        self.assertEqual(reversal.amount, self.op.amount)
        self.assertEqual(reversal.source, self.op.source)
        self.assertEqual(reversal.destination, self.op.destination)

    def test_reverse_creates_counter_transactions(self):
        self.op.reverse(officer=self.officer)

        original_txs = self.op.get_all_transactions()
        self.assertEqual(original_txs.count(), 4)  # 2 original + 2 counter

        reversed_txs = original_txs.filter(reversal_of__isnull=False)
        self.assertEqual(reversed_txs.count(), 2)

    def test_reverse_counter_transactions_flip_funds(self):
        self.op.reverse(officer=self.officer)

        original_txs = self.op.get_all_transactions().filter(reversal_of__isnull=True)
        for tx in original_txs:
            counter = tx.reversed_by
            self.assertEqual(counter.source, tx.target)
            self.assertEqual(counter.target, tx.source)
            self.assertEqual(counter.amount, tx.amount)

    def test_reverse_counter_transactions_preserve_type(self):
        self.op.reverse(officer=self.officer)

        original_txs = self.op.get_all_transactions().filter(reversal_of__isnull=True)
        for tx in original_txs:
            self.assertEqual(tx.reversed_by.type, tx.type)

    def test_shareholder_fund_restored_after_reversal(self):
        balance_after_coverage = self.shareholder.balance
        self.op.reverse(officer=self.officer)

        self.shareholder.refresh_from_db()
        self.assertEqual(
            self.shareholder.balance,
            balance_after_coverage + self.op.amount,
        )

    def test_project_fund_reduced_after_reversal(self):
        balance_after_coverage = self.project_entity.balance
        self.op.reverse(officer=self.officer)

        self.project_entity.refresh_from_db()
        self.assertEqual(
            self.project_entity.balance,
            balance_after_coverage - self.op.amount,
        )

    def test_reversal_restores_remaining_coverable(self):
        self.assertEqual(self.period.remaining_coverable, Decimal("500.00"))
        self.op.reverse(officer=self.officer)
        self.assertEqual(self.period.remaining_coverable, Decimal("1000.00"))

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    def test_cannot_reverse_already_reversed_operation(self):
        self.op.reverse(officer=self.officer)
        self.op.refresh_from_db()

        with self.assertRaises(ValidationError):
            self.op.reverse(officer=self.officer)

    def test_cannot_reverse_a_reversal(self):
        reversal = self.op.reverse(officer=self.officer)

        with self.assertRaises(ValidationError):
            reversal.reverse(officer=self.officer)
