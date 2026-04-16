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


class LossCoverageCreateTest(TestCase):
    def setUp(self):
        self.world = Entity.create(EntityType.WORLD)
        self.system = Entity.create(EntityType.SYSTEM)
        self.officer = _make_officer("officer_lc_create")
        self.project_entity = _make_project_entity("LC Create Project")
        self.shareholder = _make_shareholder_entity("LC Create Shareholder")
        _register_shareholder(self.project_entity, self.shareholder)

        # Seed shareholder with funds (also creates their financial period)
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
            amount=Decimal("300.00"),
            operation_type=OperationType.LOSS_COVERAGE,
            date=TODAY,
            plan=self.period,
            officer=self.officer,
        )
        defaults.update(kwargs)
        return LossCoverageOperation(**defaults)

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_creates_issuance_and_payment_transactions(self):
        op = self._make_op()
        op.save()

        transactions = op.get_all_transactions()
        self.assertEqual(transactions.count(), 2)
        self.assertTrue(
            transactions.filter(type=TransactionType.LOSS_COVERAGE_ISSUANCE).exists()
        )
        self.assertTrue(
            transactions.filter(type=TransactionType.LOSS_COVERAGE_PAYMENT).exists()
        )

    def test_transaction_amounts_match_operation(self):
        op = self._make_op(amount=Decimal("400.00"))
        op.save()

        for tx in op.get_all_transactions():
            self.assertEqual(tx.amount, Decimal("400.00"))

    def test_transaction_funds_flow_from_shareholder_to_project(self):
        op = self._make_op()
        op.save()

        for tx in op.get_all_transactions():
            self.assertEqual(tx.source, self.shareholder)
            self.assertEqual(tx.target, self.project_entity)

    def test_is_fully_settled_after_creation(self):
        op = self._make_op()
        op.save()

        self.assertTrue(op.is_fully_settled)
        self.assertEqual(op.amount_remaining_to_settle, Decimal("0.00"))

    def test_shareholder_fund_decreases_by_coverage_amount(self):
        balance_before = self.shareholder.balance
        op = self._make_op(amount=Decimal("500.00"))
        op.save()

        self.shareholder.refresh_from_db()
        self.assertEqual(
            self.shareholder.balance,
            balance_before - Decimal("500.00"),
        )

    def test_project_fund_increases_by_coverage_amount(self):
        balance_before = self.project_entity.balance
        op = self._make_op(amount=Decimal("500.00"))
        op.save()

        self.project_entity.refresh_from_db()
        self.assertEqual(
            self.project_entity.balance,
            balance_before + Decimal("500.00"),
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    def test_shareholder_property_returns_source(self):
        op = self._make_op()
        op.save()

        self.assertEqual(op.shareholder, self.shareholder)

    def test_project_property_returns_destination(self):
        op = self._make_op()
        op.save()

        self.assertEqual(op.project, self.project_entity)

    # ------------------------------------------------------------------
    # Plan validation
    # ------------------------------------------------------------------

    def test_plan_required(self):
        op = self._make_op(plan=None)
        with self.assertRaises(ValidationError):
            op.save()

    def test_raises_when_plan_is_profit(self):
        profit_project = _make_project_entity("LC Profit Project")
        profit_shareholder = _make_shareholder_entity("LC Profit Shareholder")
        _register_shareholder(profit_project, profit_shareholder)
        _seed_cash_injection(
            self.world, profit_shareholder, Decimal("1000.00"), self.officer
        )
        profit_period = FinancialPeriod.objects.get(entity=profit_project)
        _force_close_period(profit_period)
        FinancialPeriod(entity=profit_project, start_date=TODAY).save()

        _set_period_amount(profit_period, Decimal("500.00"))

        op = LossCoverageOperation(
            source=profit_shareholder,
            destination=profit_project,
            amount=Decimal("100.00"),
            operation_type=OperationType.LOSS_COVERAGE,
            date=TODAY,
            plan=profit_period,
            officer=self.officer,
        )
        with self.assertRaises(ValidationError):
            op.save()

    def test_raises_when_plan_is_break_even(self):
        be_project = _make_project_entity("LC BreakEven Project")
        be_shareholder = _make_shareholder_entity("LC BreakEven Shareholder")
        _register_shareholder(be_project, be_shareholder)
        _seed_cash_injection(
            self.world, be_shareholder, Decimal("1000.00"), self.officer
        )
        be_period = FinancialPeriod.objects.get(entity=be_project)
        _force_close_period(be_period)
        FinancialPeriod(entity=be_project, start_date=TODAY).save()

        _set_period_amount(be_period, Decimal("0.00"))

        op = LossCoverageOperation(
            source=be_shareholder,
            destination=be_project,
            amount=Decimal("100.00"),
            operation_type=OperationType.LOSS_COVERAGE,
            date=TODAY,
            plan=be_period,
            officer=self.officer,
        )
        with self.assertRaises(ValidationError):
            op.save()

    def test_raises_when_amount_exceeds_plan_loss(self):
        op = self._make_op(
            amount=Decimal("1001.00")
        )  # plan.amount=-1000 → coverable=1000
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

    # ------------------------------------------------------------------
    # Balance check
    # ------------------------------------------------------------------

    def test_check_balance_on_payment_is_enabled(self):
        self.assertTrue(LossCoverageOperation.check_balance_on_payment)

    def test_insufficient_shareholder_fund_balance_raises(self):
        poor_project = _make_project_entity("LC Poor Project")
        poor_shareholder = _make_shareholder_entity("LC Poor Shareholder")
        _register_shareholder(poor_project, poor_shareholder)
        # Only 100 available
        _seed_cash_injection(
            self.world, poor_shareholder, Decimal("100.00"), self.officer
        )
        poor_period = FinancialPeriod.objects.get(entity=poor_project)
        _force_close_period(poor_period)
        FinancialPeriod(entity=poor_project, start_date=TODAY).save()
        _set_period_amount(poor_period, Decimal("-500.00"))

        op = LossCoverageOperation(
            source=poor_shareholder,
            destination=poor_project,
            amount=Decimal("200.00"),  # exceeds shareholder balance of 100
            operation_type=OperationType.LOSS_COVERAGE,
            date=TODAY,
            plan=poor_period,
            officer=self.officer,
        )
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Officer validation
    # ------------------------------------------------------------------

    def test_officer_must_have_staff_user(self):
        non_staff_user = User.objects.create_user(
            username="non_staff_lc", password="x", is_staff=False
        )
        op = self._make_op(officer=non_staff_user)
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Immutability
    # ------------------------------------------------------------------

    def test_source_is_immutable(self):
        op = self._make_op()
        op.save()
        other_shareholder = _make_shareholder_entity("Other LC Source SH")
        _seed_cash_injection(
            self.world, other_shareholder, Decimal("1000.00"), self.officer
        )
        op.source = other_shareholder
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_is_immutable(self):
        op = self._make_op()
        op.save()
        other_project = _make_project_entity("Other LC Destination Project")
        op.destination = other_project
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_is_immutable(self):
        op = self._make_op()
        op.save()
        op.amount = Decimal("9999.00")
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # One-shot constraint
    # ------------------------------------------------------------------

    def test_one_shot_prevents_second_payment(self):
        op = self._make_op()
        op.save()
        with self.assertRaises(ValidationError):
            op.create_payment_transaction(
                amount=op.amount,
                officer=self.officer,
                date=TODAY,
            )


# ---------------------------------------------------------------------------
# Reversal
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
