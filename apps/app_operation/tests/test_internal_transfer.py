from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, Person
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CashInjectionOperation, InternalTransferOperation
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


def _make_officer(username="officer"):
    user = User.objects.create_user(username=username, password="testpass", is_staff=True)
    person = Person.create(private_name=f"Officer {username}", auth_user=user)
    return person.entity


def _make_internal_person(name):
    person = Person.create(private_name=name, is_internal=True)
    return person.entity


def _inject(world_entity, dest_entity, amount, officer_entity):
    CashInjectionOperation(
        source=world_entity,
        destination=dest_entity,
        amount=amount,
        operation_type=OperationType.CASH_INJECTION,
        date=date.today(),
        description="Seed balance",
        officer=officer_entity,
    ).save()


class InternalTransferCreateTest(TestCase):
    def setUp(self):
        self.world_entity = Entity.create(is_world=True)
        self.officer_entity = _make_officer()
        self.source_entity = _make_internal_person("Source Person")
        self.dest_entity = _make_internal_person("Destination Person")

        # Seed source fund so it has sufficient balance for most tests
        _inject(self.world_entity, self.source_entity, Decimal("2000.00"), self.officer_entity)

    def _make_op(self, **kwargs):
        defaults = dict(
            source=self.source_entity,
            destination=self.dest_entity,
            amount=Decimal("500.00"),
            operation_type=OperationType.INTERNAL_TRANSFER,
            date=date.today(),
            description="Test internal transfer",
            officer=self.officer_entity,
        )
        defaults.update(kwargs)
        return InternalTransferOperation(**defaults)

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
            transactions.filter(type=TransactionType.INTERNAL_TRANSFER_ISSUANCE).exists()
        )
        self.assertTrue(
            transactions.filter(type=TransactionType.INTERNAL_TRANSFER_PAYMENT).exists()
        )

    def test_transaction_funds_are_correct(self):
        op = self._make_op()
        op.save()

        for tx in op.get_all_transactions():
            self.assertEqual(tx.source, self.source_entity.fund)
            self.assertEqual(tx.target, self.dest_entity.fund)

    def test_is_fully_settled_immediately(self):
        op = self._make_op(amount=Decimal("500.00"))
        op.save()

        self.assertEqual(op.amount_settled, Decimal("500.00"))
        self.assertTrue(op.is_fully_settled)
        self.assertEqual(op.amount_remaining_to_settle, Decimal("0.00"))

    def test_source_balance_decreases_after_transfer(self):
        balance_before = self.source_entity.fund.balance

        op = self._make_op(amount=Decimal("300.00"))
        op.save()

        self.source_entity.fund.refresh_from_db()
        self.assertEqual(self.source_entity.fund.balance, balance_before - Decimal("300.00"))

    def test_destination_balance_increases_after_transfer(self):
        balance_before = self.dest_entity.fund.balance

        op = self._make_op(amount=Decimal("300.00"))
        op.save()

        self.dest_entity.fund.refresh_from_db()
        self.assertEqual(self.dest_entity.fund.balance, balance_before + Decimal("300.00"))

    # ------------------------------------------------------------------
    # Source validation
    # ------------------------------------------------------------------

    def test_non_internal_source_raises_validation_error(self):
        external = Person.create(private_name="External Person")
        op = self._make_op(source=external.entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_system_entity_as_source_raises_validation_error(self):
        system_entity = Entity.create(is_system=True)
        op = self._make_op(source=system_entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_world_entity_as_source_raises_validation_error(self):
        op = self._make_op(source=self.world_entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_must_be_active(self):
        self.source_entity.active = False
        self.source_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_fund_must_be_active(self):
        self.source_entity.fund.active = False
        self.source_entity.fund.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_insufficient_balance_raises_validation_error(self):
        op = self._make_op(amount=Decimal("9999.00"))  # exceeds 2000 seeded
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Destination validation
    # ------------------------------------------------------------------

    def test_non_internal_destination_raises_validation_error(self):
        external = Person.create(private_name="External Dest")
        op = self._make_op(destination=external.entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_system_entity_as_destination_raises_validation_error(self):
        system_entity = Entity.create(is_system=True)
        op = self._make_op(destination=system_entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_world_entity_as_destination_raises_validation_error(self):
        op = self._make_op(destination=self.world_entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_must_be_active(self):
        self.dest_entity.active = False
        self.dest_entity.save()

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

    # ------------------------------------------------------------------
    # Officer validation
    # ------------------------------------------------------------------

    def test_officer_must_be_personal_entity(self):
        system_entity = Entity.create(is_system=True)
        op = self._make_op(officer=system_entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_officer_must_have_user(self):
        no_user_person = Person.create(private_name="No User Officer")
        op = self._make_op(officer=no_user_person.entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_officer_user_must_be_staff(self):
        non_staff_user = User.objects.create_user(
            username="non_staff", password="testpass", is_staff=False
        )
        non_staff_person = Person.create(
            private_name="Non Staff Officer", auth_user=non_staff_user
        )
        op = self._make_op(officer=non_staff_person.entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_officer_must_be_active(self):
        self.officer_entity.active = False
        self.officer_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Immutability
    # ------------------------------------------------------------------

    def test_source_is_immutable(self):
        op = self._make_op()
        op.save()

        other = _make_internal_person("Other Source")
        _inject(self.world_entity, other, Decimal("1000.00"), self.officer_entity)
        op.source = other
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_is_immutable(self):
        op = self._make_op()
        op.save()

        other = _make_internal_person("Other Dest")
        op.destination = other
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
                officer=self.officer_entity,
                date=date.today(),
            )


class InternalTransferReversalTest(TestCase):
    def setUp(self):
        self.world_entity = Entity.create(is_world=True)
        self.officer_entity = _make_officer()
        self.source_entity = _make_internal_person("Source Person")
        self.dest_entity = _make_internal_person("Destination Person")

        _inject(self.world_entity, self.source_entity, Decimal("2000.00"), self.officer_entity)

        self.op = InternalTransferOperation(
            source=self.source_entity,
            destination=self.dest_entity,
            amount=Decimal("500.00"),
            operation_type=OperationType.INTERNAL_TRANSFER,
            date=date.today(),
            description="Test internal transfer",
            officer=self.officer_entity,
        )
        self.op.save()

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_reverse_creates_reversal_operation(self):
        reversal = self.op.reverse(officer=self.officer_entity)

        self.assertIsNotNone(reversal.pk)
        self.assertEqual(reversal.reversal_of, self.op)

    def test_reverse_marks_original_as_reversed(self):
        reversal = self.op.reverse(officer=self.officer_entity)

        self.op.refresh_from_db()
        self.assertTrue(self.op.is_reversed)
        self.assertEqual(self.op.reversed_by, reversal)

    def test_reversal_is_reversal(self):
        reversal = self.op.reverse(officer=self.officer_entity)

        self.assertTrue(reversal.is_reversal)
        self.assertFalse(reversal.is_reversed)

    def test_reverse_inherits_amount_source_destination(self):
        reversal = self.op.reverse(officer=self.officer_entity)

        self.assertEqual(reversal.amount, self.op.amount)
        self.assertEqual(reversal.source, self.op.source)
        self.assertEqual(reversal.destination, self.op.destination)

    def test_reverse_creates_counter_transactions(self):
        self.op.reverse(officer=self.officer_entity)

        original_txs = self.op.get_all_transactions()
        self.assertEqual(original_txs.count(), 4)  # 2 original + 2 counter

        reversed_txs = original_txs.filter(reversal_of__isnull=False)
        self.assertEqual(reversed_txs.count(), 2)

    def test_reverse_counter_transactions_flip_funds(self):
        self.op.reverse(officer=self.officer_entity)

        original_txs = self.op.get_all_transactions().filter(reversal_of__isnull=True)
        for tx in original_txs:
            counter = tx.reversed_by
            self.assertEqual(counter.source, tx.target)
            self.assertEqual(counter.target, tx.source)
            self.assertEqual(counter.amount, tx.amount)

    def test_reverse_counter_transactions_preserve_type(self):
        self.op.reverse(officer=self.officer_entity)

        original_txs = self.op.get_all_transactions().filter(reversal_of__isnull=True)
        for tx in original_txs:
            self.assertEqual(tx.reversed_by.type, tx.type)

    def test_source_balance_restored_after_reversal(self):
        balance_after_transfer = self.source_entity.fund.balance
        self.op.reverse(officer=self.officer_entity)

        self.source_entity.fund.refresh_from_db()
        self.assertEqual(
            self.source_entity.fund.balance,
            balance_after_transfer + self.op.amount,
        )

    def test_destination_balance_restored_after_reversal(self):
        balance_after_transfer = self.dest_entity.fund.balance
        self.op.reverse(officer=self.officer_entity)

        self.dest_entity.fund.refresh_from_db()
        self.assertEqual(
            self.dest_entity.fund.balance,
            balance_after_transfer - self.op.amount,
        )

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    def test_cannot_reverse_already_reversed_operation(self):
        self.op.reverse(officer=self.officer_entity)
        self.op.refresh_from_db()

        with self.assertRaises(ValidationError):
            self.op.reverse(officer=self.officer_entity)

    def test_cannot_reverse_a_reversal(self):
        reversal = self.op.reverse(officer=self.officer_entity)

        with self.assertRaises(ValidationError):
            reversal.reverse(officer=self.officer_entity)
