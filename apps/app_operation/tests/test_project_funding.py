from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, Person, Project, Stakeholder, StakeholderRole
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CashInjectionOperation, ProjectFundingOperation
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


class ProjectFundingCreateTest(TestCase):
    def setUp(self):
        self.world_entity = Entity.create(is_world=True)

        self.officer = User.objects.create_user(
            username="officer", password="testpass", is_staff=True
        )

        # Funder: person entity
        funder_person = Person.create(private_name="Funder Person")
        self.funder_entity = funder_person.entity

        # Project entity
        project = Project(name="Test Project")
        project.save()
        self.project_entity = Entity.create(owner=project)

        # Register funder as shareholder of the project
        Stakeholder(
            parent=self.project_entity,
            target=self.funder_entity,
            role=StakeholderRole.SHAREHOLDER,
        ).save()

        # Fund the funder so balance-dependent tests work
        self._inject(Decimal("2000.00"))

    def _inject(self, amount):
        op = CashInjectionOperation(
            source=self.world_entity,
            destination=self.funder_entity,
            amount=amount,
            operation_type=OperationType.CASH_INJECTION,
            date=date.today(),
            description="Setup injection",
            officer=self.officer,
        )
        op.save()
        return op

    def _make_op(self, **kwargs):
        defaults = dict(
            source=self.funder_entity,
            destination=self.project_entity,
            amount=Decimal("500.00"),
            operation_type=OperationType.PROJECT_FUNDING,
            date=date.today(),
            description="Test project funding",
            officer=self.officer,
        )
        defaults.update(kwargs)
        return ProjectFundingOperation(**defaults)

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_creates_issuance_and_payment_transactions(self):
        op = self._make_op()
        op.save()

        self.assertIsNotNone(op.pk)
        self.assertIsNotNone(op.source.person)
        self.assertIsNotNone(op.destination.project)

        transactions = op.get_all_transactions()
        self.assertEqual(transactions.count(), 2)

        self.assertTrue(
            transactions.filter(type=TransactionType.PROJECT_FUNDING_ISSUANCE).exists(),
            "Issuance transaction should be created",
        )
        self.assertTrue(
            transactions.filter(type=TransactionType.PROJECT_FUNDING_PAYMENT).exists(),
            "Payment transaction should be created",
        )

    def test_transaction_amounts_match_operation(self):
        op = self._make_op(amount=Decimal("300.00"))
        op.save()

        for tx in op.get_all_transactions():
            self.assertEqual(tx.amount, Decimal("300.00"))

    def test_transaction_funds_are_correct(self):
        op = self._make_op()
        op.save()

        for tx in op.get_all_transactions():
            self.assertEqual(tx.source, self.funder_entity.fund)
            self.assertEqual(tx.target, self.project_entity.fund)

    # ------------------------------------------------------------------
    # Settlement state
    # ------------------------------------------------------------------

    def test_is_fully_settled_after_creation(self):
        op = self._make_op(amount=Decimal("500.00"))
        op.save()

        self.assertEqual(op.amount_settled, Decimal("500.00"))
        self.assertTrue(op.is_fully_settled)
        self.assertEqual(op.amount_remaining_to_settle, Decimal("0.00"))

    # ------------------------------------------------------------------
    # Source / destination validation
    # ------------------------------------------------------------------

    def test_source_must_be_person_entity(self):
        non_person = Entity.create(is_world=False, owner=Project.objects.create(name="Another Project"))
        # Register it as shareholder just to isolate the person check
        Stakeholder(
            parent=self.project_entity,
            target=non_person,
            role=StakeholderRole.SHAREHOLDER,
        )  # intentionally not saved; source type check happens first
        op = self._make_op(source=self.project_entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_must_be_shareholder_of_destination_project(self):
        non_shareholder_person = Person.create(private_name="Non Shareholder")
        self._inject_to(non_shareholder_person.entity, Decimal("1000.00"))

        op = self._make_op(source=non_shareholder_person.entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_must_be_project_entity(self):
        other_person = Person.create(private_name="Wrong Destination")
        op = self._make_op(destination=other_person.entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_entity_must_be_active(self):
        self.funder_entity.active = False
        self.funder_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_entity_must_be_active(self):
        self.project_entity.active = False
        self.project_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_fund_must_be_active(self):
        self.funder_entity.fund.active = False
        self.funder_entity.fund.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Amount validation
    # ------------------------------------------------------------------

    def test_amount_zero_raises_validation_error(self):
        op = self._make_op(amount=Decimal("0.00"))
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_negative_raises_validation_error(self):
        op = self._make_op(amount=Decimal("-100.00"))
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_exceeding_funder_balance_raises_error(self):
        balance = self.funder_entity.fund.balance  # 2000.00 from setUp

        op = self._make_op(amount=balance + Decimal("1.00"))
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_equal_to_funder_balance_succeeds(self):
        balance = self.funder_entity.fund.balance  # 2000.00 from setUp

        op = self._make_op(amount=balance)
        op.save()  # should not raise
        self.assertIsNotNone(op.pk)

    # ------------------------------------------------------------------
    # Officer validation
    # ------------------------------------------------------------------

    def test_officer_user_must_be_staff(self):
        non_staff_user = User.objects.create_user(
            username="non_staff", password="testpass", is_staff=False
        )
        op = self._make_op(officer=non_staff_user)
        with self.assertRaises(ValidationError):
            op.save()

    def test_officer_must_be_active(self):
        self.officer.is_active = False
        self.officer.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Immutability
    # ------------------------------------------------------------------

    def test_source_is_immutable(self):
        other_funder = Person.create(private_name="Other Funder")
        Stakeholder(
            parent=self.project_entity,
            target=other_funder.entity,
            role=StakeholderRole.SHAREHOLDER,
        ).save()
        self._inject_to(other_funder.entity, Decimal("1000.00"))

        op = self._make_op()
        op.save()

        op.source = other_funder.entity
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_is_immutable(self):
        other_project = Project.objects.create(name="Other Project")
        other_project_entity = Entity.create(owner=other_project)

        op = self._make_op()
        op.save()

        op.destination = other_project_entity
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
                date=date.today(),
            )

    # ------------------------------------------------------------------
    # Balance
    # ------------------------------------------------------------------

    def test_project_fund_increases_after_funding(self):
        balance_before = self.project_entity.fund.balance

        op = self._make_op(amount=Decimal("700.00"))
        op.save()

        self.assertEqual(
            self.project_entity.fund.balance,
            balance_before + Decimal("700.00"),
        )

    def test_funder_fund_decreases_after_funding(self):
        balance_before = self.funder_entity.fund.balance

        op = self._make_op(amount=Decimal("700.00"))
        op.save()

        self.assertEqual(
            self.funder_entity.fund.balance,
            balance_before - Decimal("700.00"),
        )

    # ------------------------------------------------------------------
    # check_balance_on_payment
    # ------------------------------------------------------------------

    def test_check_balance_on_payment_is_disabled(self):
        """Balance is enforced by clean() at creation; no per-payment gate needed."""
        self.assertFalse(ProjectFundingOperation.check_balance_on_payment)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _inject_to(self, entity, amount):
        CashInjectionOperation(
            source=self.world_entity,
            destination=entity,
            amount=amount,
            operation_type=OperationType.CASH_INJECTION,
            date=date.today(),
            description="Setup injection",
            officer=self.officer,
        ).save()


class ProjectFundingReversalTest(TestCase):
    def setUp(self):
        self.world_entity = Entity.create(is_world=True)

        self.officer = User.objects.create_user(
            username="officer", password="testpass", is_staff=True
        )

        funder_person = Person.create(private_name="Funder Person")
        self.funder_entity = funder_person.entity

        project = Project(name="Test Project")
        project.save()
        self.project_entity = Entity.create(owner=project)

        Stakeholder(
            parent=self.project_entity,
            target=self.funder_entity,
            role=StakeholderRole.SHAREHOLDER,
        ).save()

        # Fund the funder
        CashInjectionOperation(
            source=self.world_entity,
            destination=self.funder_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.CASH_INJECTION,
            date=date.today(),
            description="Setup injection",
            officer=self.officer,
        ).save()

        self.op = ProjectFundingOperation(
            source=self.funder_entity,
            destination=self.project_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.PROJECT_FUNDING,
            date=date.today(),
            description="Test project funding",
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
        reversal = self.op.reverse(officer=self.officer)

        original_txs = self.op.get_all_transactions()
        self.assertEqual(original_txs.count(), 4)  # 2 original + 2 counter-transactions

        reversal_txs = reversal.get_all_transactions()
        self.assertEqual(reversal_txs.count(), 0)  # reversal op owns no transactions

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

    # ------------------------------------------------------------------
    # Balance restoration
    # ------------------------------------------------------------------

    def test_project_fund_restored_after_reversal(self):
        balance_after_funding = self.project_entity.fund.balance
        self.op.reverse(officer=self.officer)

        self.assertEqual(
            self.project_entity.fund.balance,
            balance_after_funding - self.op.amount,
        )

    def test_funder_fund_restored_after_reversal(self):
        balance_after_funding = self.funder_entity.fund.balance
        self.op.reverse(officer=self.officer)

        self.assertEqual(
            self.funder_entity.fund.balance,
            balance_after_funding + self.op.amount,
        )
