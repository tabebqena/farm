from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import QuerySet as DjangoQuerySet
from django.test import TestCase

from apps.app_entity.models import Entity, Person, Project, Stakeholder, StakeholderRole
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.period import FinancialPeriod
from apps.app_operation.models.proxies import CapitalGainOperation, ProfitDistributionOperation
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
LAST_MONTH = TODAY - timedelta(days=30)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_officer(username):
    user = User.objects.create_user(username=username, password="x", is_staff=True)
    person = Person.create(private_name=f"Officer {username}", auth_user=user)
    return person.entity


def _make_project_entity(name):
    project = Project(name=name)
    project.save()
    return Entity.create(owner=project)


def _make_shareholder_entity(name):
    person = Person.create(private_name=name)
    entity = person.entity
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


def _seed_capital_gain(system, destination, amount, officer):
    CapitalGainOperation(
        source=system,
        destination=destination,
        amount=amount,
        operation_type=OperationType.CAPITAL_GAIN,
        date=TODAY,
        officer=officer,
    ).save()


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class ProfitDistributionCreateTest(TestCase):
    def setUp(self):
        self.system = Entity.create(is_system=True)
        self.officer = _make_officer("officer_pd_create")
        self.project_entity = _make_project_entity("PD Create Project")
        self.shareholder = _make_shareholder_entity("PD Create Shareholder")
        _register_shareholder(self.project_entity, self.shareholder)

        _seed_capital_gain(self.system, self.project_entity, Decimal("2000.00"), self.officer)

        self.period = FinancialPeriod.objects.get(entity=self.project_entity)
        _force_close_period(self.period)
        FinancialPeriod(entity=self.project_entity, start_date=TODAY).save()

        _set_period_amount(self.period, Decimal("1000.00"))

    def _make_op(self, **kwargs):
        defaults = dict(
            source=self.project_entity,
            destination=self.shareholder,
            amount=Decimal("300.00"),
            operation_type=OperationType.PROFIT_DISTRIBUTION,
            date=TODAY,
            plan=self.period,
            officer=self.officer,
        )
        defaults.update(kwargs)
        return ProfitDistributionOperation(**defaults)

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_creates_issuance_and_payment_transactions(self):
        op = self._make_op()
        op.save()

        transactions = op.get_all_transactions()
        self.assertEqual(transactions.count(), 2)
        self.assertTrue(
            transactions.filter(type=TransactionType.PROFIT_DISTRIBUTION_ISSUANCE).exists()
        )
        self.assertTrue(
            transactions.filter(type=TransactionType.PROFIT_DISTRIBUTION_PAYMENT).exists()
        )

    def test_transaction_amounts_match_operation(self):
        op = self._make_op(amount=Decimal("400.00"))
        op.save()

        for tx in op.get_all_transactions():
            self.assertEqual(tx.amount, Decimal("400.00"))

    def test_transaction_funds_flow_from_project_to_shareholder(self):
        op = self._make_op()
        op.save()

        for tx in op.get_all_transactions():
            self.assertEqual(tx.source, self.project_entity.fund)
            self.assertEqual(tx.target, self.shareholder.fund)

    def test_is_fully_settled_after_creation(self):
        op = self._make_op()
        op.save()

        self.assertTrue(op.is_fully_settled)
        self.assertEqual(op.amount_remaining_to_settle, Decimal("0.00"))

    def test_project_fund_decreases_by_distribution_amount(self):
        balance_before = self.project_entity.fund.balance
        op = self._make_op(amount=Decimal("500.00"))
        op.save()

        self.assertEqual(
            self.project_entity.fund.balance,
            balance_before - Decimal("500.00"),
        )

    def test_shareholder_fund_increases_by_distribution_amount(self):
        balance_before = self.shareholder.fund.balance
        op = self._make_op(amount=Decimal("500.00"))
        op.save()

        self.assertEqual(
            self.shareholder.fund.balance,
            balance_before + Decimal("500.00"),
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    def test_project_property_returns_source(self):
        op = self._make_op()
        op.save()

        self.assertEqual(op.project, self.project_entity)

    def test_shareholder_property_returns_destination(self):
        op = self._make_op()
        op.save()

        self.assertEqual(op.shareholder, self.shareholder)

    # ------------------------------------------------------------------
    # Source validation
    # ------------------------------------------------------------------

    def test_source_must_be_project_entity(self):
        non_project = Person.create(private_name="PD Non-project").entity
        op = self._make_op(source=non_project)
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Destination validation
    # ------------------------------------------------------------------

    def test_destination_must_be_shareholder(self):
        non_shareholder = Person.create(private_name="PD Non-SH").entity
        op = self._make_op(destination=non_shareholder)
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Plan validation
    # ------------------------------------------------------------------

    def test_plan_required(self):
        op = self._make_op(plan=None)
        with self.assertRaises(ValidationError):
            op.save()

    def test_raises_when_plan_is_loss(self):
        loss_project = _make_project_entity("PD Loss Project")
        loss_shareholder = _make_shareholder_entity("PD Loss Shareholder")
        _register_shareholder(loss_project, loss_shareholder)
        loss_period = FinancialPeriod.objects.get(entity=loss_project)
        _force_close_period(loss_period)
        FinancialPeriod(entity=loss_project, start_date=TODAY).save()
        _set_period_amount(loss_period, Decimal("-400.00"))

        op = ProfitDistributionOperation(
            source=loss_project,
            destination=loss_shareholder,
            amount=Decimal("100.00"),
            operation_type=OperationType.PROFIT_DISTRIBUTION,
            date=TODAY,
            plan=loss_period,
            officer=self.officer,
        )
        with self.assertRaises(ValidationError):
            op.save()

    def test_raises_when_plan_is_break_even(self):
        be_project = _make_project_entity("PD BreakEven Project")
        be_shareholder = _make_shareholder_entity("PD BreakEven Shareholder")
        _register_shareholder(be_project, be_shareholder)
        _seed_capital_gain(self.system, be_project, Decimal("500.00"), self.officer)
        be_period = FinancialPeriod.objects.get(entity=be_project)
        _force_close_period(be_period)
        FinancialPeriod(entity=be_project, start_date=TODAY).save()
        _set_period_amount(be_period, Decimal("0.00"))

        op = ProfitDistributionOperation(
            source=be_project,
            destination=be_shareholder,
            amount=Decimal("100.00"),
            operation_type=OperationType.PROFIT_DISTRIBUTION,
            date=TODAY,
            plan=be_period,
            officer=self.officer,
        )
        with self.assertRaises(ValidationError):
            op.save()

    def test_raises_when_amount_exceeds_plan(self):
        op = self._make_op(amount=Decimal("1001.00"))  # plan.amount = 1000
        with self.assertRaises(ValidationError):
            op.save()

    def test_raises_when_amount_exceeds_remaining_after_partial_distribution(self):
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
        self.assertTrue(ProfitDistributionOperation.check_balance_on_payment)

    def test_insufficient_project_fund_balance_raises(self):
        # Project funded with only 100; try to distribute 200
        small_project = _make_project_entity("PD Small Project")
        small_shareholder = _make_shareholder_entity("PD Small Shareholder")
        _register_shareholder(small_project, small_shareholder)
        _seed_capital_gain(self.system, small_project, Decimal("100.00"), self.officer)
        small_period = FinancialPeriod.objects.get(entity=small_project)
        _force_close_period(small_period)
        FinancialPeriod(entity=small_project, start_date=TODAY).save()
        _set_period_amount(small_period, Decimal("500.00"))

        op = ProfitDistributionOperation(
            source=small_project,
            destination=small_shareholder,
            amount=Decimal("200.00"),
            operation_type=OperationType.PROFIT_DISTRIBUTION,
            date=TODAY,
            plan=small_period,
            officer=self.officer,
        )
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Officer validation
    # ------------------------------------------------------------------

    def test_officer_must_have_staff_user(self):
        non_staff_user = User.objects.create_user(
            username="non_staff_pd", password="x", is_staff=False
        )
        non_staff_person = Person.create(private_name="Non Staff PD", auth_user=non_staff_user)
        op = self._make_op(officer=non_staff_person.entity)
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Immutability
    # ------------------------------------------------------------------

    def test_source_is_immutable(self):
        op = self._make_op()
        op.save()
        other_project = _make_project_entity("Other PD Source Project")
        op.source = other_project
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_is_immutable(self):
        op = self._make_op()
        op.save()
        other_shareholder = _make_shareholder_entity("Other PD Destination SH")
        op.destination = other_shareholder
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


class ProfitDistributionReversalTest(TestCase):
    def setUp(self):
        self.system = Entity.create(is_system=True)
        self.officer = _make_officer("officer_pd_rev")
        self.project_entity = _make_project_entity("PD Reversal Project")
        self.shareholder = _make_shareholder_entity("PD Reversal Shareholder")
        _register_shareholder(self.project_entity, self.shareholder)

        _seed_capital_gain(self.system, self.project_entity, Decimal("2000.00"), self.officer)

        self.period = FinancialPeriod.objects.get(entity=self.project_entity)
        _force_close_period(self.period)
        FinancialPeriod(entity=self.project_entity, start_date=TODAY).save()

        _set_period_amount(self.period, Decimal("1000.00"))

        self.op = ProfitDistributionOperation(
            source=self.project_entity,
            destination=self.shareholder,
            amount=Decimal("500.00"),
            operation_type=OperationType.PROFIT_DISTRIBUTION,
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

    def test_project_fund_restored_after_reversal(self):
        balance_after_distribution = self.project_entity.fund.balance
        self.op.reverse(officer=self.officer)

        self.assertEqual(
            self.project_entity.fund.balance,
            balance_after_distribution + self.op.amount,
        )

    def test_shareholder_fund_reduced_after_reversal(self):
        balance_after_distribution = self.shareholder.fund.balance
        self.op.reverse(officer=self.officer)

        self.assertEqual(
            self.shareholder.fund.balance,
            balance_after_distribution - self.op.amount,
        )

    def test_reversal_restores_remaining_distributable(self):
        self.assertEqual(self.period.remaining_distributable, Decimal("500.00"))
        self.op.reverse(officer=self.officer)
        self.assertEqual(self.period.remaining_distributable, Decimal("1000.00"))

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
