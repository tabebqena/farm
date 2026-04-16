from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, Person, Project
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CashInjectionOperation
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


class CashInjectionCreateTest(TestCase):
    def setUp(self):
        # Source: world entity
        self.world_entity = Entity.create(is_world=True)

        # Officer: staff user linked to a person entity
        self.officer_user = User.objects.create_user(
            username="officer", password="testpass", is_staff=True
        )

        # Receiver: person entity (has person, no project)
        receiver_person = Person.create(private_name="Receiver Person")
        self.receiver_entity = receiver_person.entity

    def _make_op(self, **kwargs):
        defaults = dict(
            source=self.world_entity,
            destination=self.receiver_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.CASH_INJECTION,
            date=date.today(),
            description="Test cash injection",
            officer=self.officer_user,
        )
        defaults.update(kwargs)
        return CashInjectionOperation(**defaults)

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_creates_issuance_and_payment_transactions(self):
        op = self._make_op()
        op.save()

        self.assertIsNotNone(op.pk)
        self.assertTrue(op.source.is_world)
        self.assertIsNotNone(op.destination.person)
        self.assertIsNone(op.destination.project)

        transactions = op.get_all_transactions()
        self.assertEqual(transactions.count(), 2)

        self.assertTrue(
            transactions.filter(type=TransactionType.CASH_INJECTION_ISSUANCE).exists(),
            "Issuance transaction should be created",
        )
        self.assertTrue(
            transactions.filter(type=TransactionType.CASH_INJECTION_PAYMENT).exists(),
            "Payment transaction should be created",
        )

    def test_transaction_amounts_match_operation(self):
        op = self._make_op(amount=Decimal("750.00"))
        op.save()

        for tx in op.get_all_transactions():
            self.assertEqual(tx.amount, Decimal("750.00"))

    def test_transaction_funds_are_correct(self):
        op = self._make_op()
        op.save()

        expected_source = self.world_entity.fund
        expected_target = self.receiver_entity.fund

        for tx in op.get_all_transactions():
            self.assertEqual(tx.source, expected_source)
            self.assertEqual(tx.target, expected_target)

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

    def test_source_must_be_world(self):
        non_world_person = Person.create(private_name="Non World Person")
        non_world_entity = Entity.objects.get(person=non_world_person)

        op = self._make_op(source=non_world_entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_must_be_person_entity(self):
        project = Project(name="Test Project")
        project.save()
        project_entity = Entity.create(owner=project)

        op = self._make_op(destination=project_entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_entity_must_be_active(self):
        self.world_entity.active = False
        self.world_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_entity_must_be_active(self):
        self.receiver_entity.active = False
        self.receiver_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_entity_must_be_able_to_pay(self):
        self.world_entity.fund.active = False
        self.world_entity.fund.save()

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
        other_person = Person.create(private_name="Other Source Person")
        op = self._make_op()
        op.save()

        op.source = other_person.entity
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_is_immutable(self):
        other_person = Person.create(private_name="Other Dest Person")
        op = self._make_op()
        op.save()

        op.destination = other_person.entity
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
        """Payer is the world entity; balance is not enforced before issuing payment."""
        self.assertFalse(CashInjectionOperation.check_balance_on_payment)

    def test_injection_succeeds_regardless_of_prior_injections(self):
        """World entity is never balance-checked; injection proceeds without limit."""
        op = self._make_op(amount=Decimal("9_999_999.00"))
        op.save()
        self.assertIsNotNone(op.pk)

    # ------------------------------------------------------------------
    # Balance
    # ------------------------------------------------------------------

    def test_receiver_balance_increases_after_cash_injection(self):
        balance_before = self.receiver_entity.fund.balance

        op = self._make_op(amount=Decimal("1000.00"))
        op.save()

        self.assertEqual(
            self.receiver_entity.fund.balance,
            balance_before + Decimal("1000.00"),
        )


class CashInjectionReversalTest(TestCase):
    def setUp(self):
        self.world_entity = Entity.create(is_world=True)

        self.officer_user = User.objects.create_user(
            username="officer", password="testpass", is_staff=True
        )

        receiver_person = Person.create(private_name="Receiver Person")
        self.receiver_entity = receiver_person.entity

        self.op = CashInjectionOperation(
            source=self.world_entity,
            destination=self.receiver_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.CASH_INJECTION,
            date=date.today(),
            description="Test cash injection",
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
        reversal = self.op.reverse(officer=self.officer_user)

        # Counter-transactions are linked to the original op (same content_type + object_id),
        # not to the reversal op. The reversal op's save() skips transaction creation.
        original_txs = self.op.get_all_transactions()
        self.assertEqual(original_txs.count(), 4)  # 2 original + 2 counter-transactions

        reversal_txs = reversal.get_all_transactions()
        self.assertEqual(reversal_txs.count(), 0)  # reversal op owns no transactions

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

    # ------------------------------------------------------------------
    # Balance
    # ------------------------------------------------------------------

    def test_receiver_balance_restored_to_zero_after_reversal(self):
        # setUp already saved the operation, so balance is already 1000 here.
        balance_after_injection = self.receiver_entity.fund.balance
        self.op.reverse(officer=self.officer_user)

        self.assertEqual(
            self.receiver_entity.fund.balance,
            balance_after_injection - self.op.amount,
        )
