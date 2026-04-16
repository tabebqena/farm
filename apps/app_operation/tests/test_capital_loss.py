from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, Person, Project
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CapitalLossOperation
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


class CapitalLossCreateTest(TestCase):
    def setUp(self):
        self.system_entity = Entity.create(is_system=True)

        self.officer_user = User.objects.create_user(
            username="officer", password="testpass", is_staff=True
        )

        # Source: active project entity
        project = Project(name="Test Project")
        project.save()
        self.project_entity = Entity.create(owner=project)

    def _make_op(self, **kwargs):
        defaults = dict(
            source=self.project_entity,
            destination=self.system_entity,
            amount=Decimal("500.00"),
            operation_type=OperationType.CAPITAL_LOSS,
            date=date.today(),
            description="Test capital loss",
            officer=self.officer_user,
        )
        defaults.update(kwargs)
        return CapitalLossOperation(**defaults)

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_creates_issuance_and_payment_transactions(self):
        op = self._make_op()
        op.save()

        self.assertIsNotNone(op.pk)

        transactions = op.get_all_transactions()
        self.assertEqual(transactions.count(), 2)

        self.assertTrue(
            transactions.filter(type=TransactionType.CAPITAL_LOSS_ISSUANCE).exists(),
            "Issuance transaction should be created",
        )
        self.assertTrue(
            transactions.filter(type=TransactionType.CAPITAL_LOSS_PAYMENT).exists(),
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
            self.assertEqual(tx.source, self.project_entity.fund)
            self.assertEqual(tx.target, self.system_entity.fund)

    def test_is_fully_settled_after_creation(self):
        op = self._make_op(amount=Decimal("500.00"))
        op.save()

        self.assertEqual(op.amount_settled, Decimal("500.00"))
        self.assertTrue(op.is_fully_settled)
        self.assertEqual(op.amount_remaining_to_settle, Decimal("0.00"))

    def test_project_fund_decreases_by_loss_amount(self):
        # Seed some balance so the project can absorb the loss
        from apps.app_operation.models.proxies import CapitalGainOperation

        seed = CapitalGainOperation(
            source=self.system_entity,
            destination=self.project_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.CAPITAL_GAIN,
            date=date.today(),
            description="Seed balance",
            officer=self.officer_user,
        )
        seed.save()

        balance_before = self.project_entity.fund.balance

        op = self._make_op(amount=Decimal("750.00"))
        op.save()

        self.project_entity.fund.refresh_from_db()
        self.assertEqual(
            self.project_entity.fund.balance,
            balance_before - Decimal("750.00"),
        )

    # ------------------------------------------------------------------
    # Source validation
    # ------------------------------------------------------------------

    def test_source_system_entity_raises_validation_error(self):
        op = self._make_op(source=self.system_entity, destination=self.system_entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_project_must_be_active(self):
        self.project_entity.active = False
        self.project_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_fund_must_be_active(self):
        self.project_entity.fund.active = False
        self.project_entity.fund.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Destination validation
    # ------------------------------------------------------------------

    def test_destination_must_be_system_entity(self):
        non_system_person = Person.create(private_name="Non System Person")
        op = self._make_op(destination=non_system_person.entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_world_entity_raises_validation_error(self):
        world_entity = Entity.create(is_world=True)
        op = self._make_op(destination=world_entity)
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
        self.officer_user.is_active = False
        self.officer_user.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Immutability
    # ------------------------------------------------------------------

    def test_source_is_immutable(self):
        op = self._make_op()
        op.save()

        other_project = Project(name="Other Project")
        other_project.save()
        other_entity = Entity.create(owner=other_project)

        op.source = other_entity
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_is_immutable(self):
        op = self._make_op()
        op.save()

        other_project = Project(name="Other Project")
        other_project.save()
        other_entity = Entity.create(owner=other_project)

        op.destination = other_entity
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
                officer=self.officer_user,
                date=date.today(),
            )

    # ------------------------------------------------------------------
    # check_balance_on_payment
    # ------------------------------------------------------------------

    def test_check_balance_on_payment_is_disabled(self):
        """Destination is the system entity; no fund balance gate on payment."""
        self.assertFalse(CapitalLossOperation.check_balance_on_payment)


class CapitalLossReversalTest(TestCase):
    def setUp(self):
        self.system_entity = Entity.create(is_system=True)

        self.officer_user = User.objects.create_user(
            username="officer", password="testpass", is_staff=True
        )

        project = Project(name="Test Project")
        project.save()
        self.project_entity = Entity.create(owner=project)

        self.op = CapitalLossOperation(
            source=self.project_entity,
            destination=self.system_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.CAPITAL_LOSS,
            date=date.today(),
            description="Test capital loss",
            officer=self.officer_user,
        )
        self.op.save()

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_reverse_creates_reversal_operation(self):
        reversal = self.op.reverse(officer=self.officer_user)

        self.assertIsNotNone(reversal.pk)
        self.assertEqual(reversal.reversal_of, self.op)

    def test_reverse_marks_original_as_reversed(self):
        reversal = self.op.reverse(officer=self.officer_user)

        self.op.refresh_from_db()
        self.assertTrue(self.op.is_reversed)
        self.assertEqual(self.op.reversed_by, reversal)

    def test_reversal_is_reversal(self):
        reversal = self.op.reverse(officer=self.officer_user)

        self.assertTrue(reversal.is_reversal)
        self.assertFalse(reversal.is_reversed)

    def test_reverse_inherits_amount_source_destination(self):
        reversal = self.op.reverse(officer=self.officer_user)

        self.assertEqual(reversal.amount, self.op.amount)
        self.assertEqual(reversal.source, self.op.source)
        self.assertEqual(reversal.destination, self.op.destination)

    def test_reverse_creates_counter_transactions(self):
        self.op.reverse(officer=self.officer_user)

        original_txs = self.op.get_all_transactions()
        self.assertEqual(original_txs.count(), 4)  # 2 original + 2 counter-transactions

        reversed_txs = original_txs.filter(reversal_of__isnull=False)
        self.assertEqual(reversed_txs.count(), 2)

    def test_reverse_counter_transactions_flip_funds(self):
        self.op.reverse(officer=self.officer_user)

        original_txs = self.op.get_all_transactions().filter(reversal_of__isnull=True)
        for tx in original_txs:
            counter = tx.reversed_by
            self.assertEqual(counter.source, tx.target)
            self.assertEqual(counter.target, tx.source)
            self.assertEqual(counter.amount, tx.amount)

    def test_reverse_counter_transactions_preserve_type(self):
        self.op.reverse(officer=self.officer_user)

        original_txs = self.op.get_all_transactions().filter(reversal_of__isnull=True)
        for tx in original_txs:
            self.assertEqual(tx.reversed_by.type, tx.type)

    def test_project_fund_restored_after_reversal(self):
        balance_after_loss = self.project_entity.fund.balance
        self.op.reverse(officer=self.officer_user)

        self.project_entity.fund.refresh_from_db()
        self.assertEqual(
            self.project_entity.fund.balance,
            balance_after_loss + self.op.amount,
        )

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    def test_cannot_reverse_already_reversed_operation(self):
        self.op.reverse(officer=self.officer_user)
        self.op.refresh_from_db()

        with self.assertRaises(ValidationError):
            self.op.reverse(officer=self.officer_user)

    def test_cannot_reverse_a_reversal(self):
        reversal = self.op.reverse(officer=self.officer_user)

        with self.assertRaises(ValidationError):
            reversal.reverse(officer=self.officer_user)
