from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from apps.app_entity.models import Entity, EntityType
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import (

    CashInjectionOperation,
    CashWithdrawalOperation,
)
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()



class CashWithdrawalCreateTest(TestCase):
    def setUp(self):
        self.world_entity = Entity.create(EntityType.WORLD)

        self.officer_user = User.objects.create_user(
            username="officer", password="testpass", is_staff=True
        )

        # Withdrawer: person entity (source of withdrawal)
        self.withdrawer_entity = Entity.create(
            EntityType.PERSON, name="Withdrawer Person"
        )

        # Fund the withdrawer's account so withdrawal can succeed
        self._inject(Decimal("2000.00"))

    def _inject(self, amount):
        op = CashInjectionOperation(
            source=self.world_entity,
            destination=self.withdrawer_entity,
            amount=amount,
            operation_type=OperationType.CASH_INJECTION,
            date=date.today(),
            description="Setup injection",
            officer=self.officer_user,
        )
        op.save()
        return op

    def _make_op(self, **kwargs):
        defaults = dict(
            source=self.withdrawer_entity,
            destination=self.world_entity,
            amount=Decimal("500.00"),
            operation_type=OperationType.CASH_WITHDRAWAL,
            date=date.today(),
            description="Test cash withdrawal",
            officer=self.officer_user,
        )
        defaults.update(kwargs)
        return CashWithdrawalOperation(**defaults)

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_creates_issuance_and_payment_transactions(self):
        op = self._make_op()
        op.save()

        self.assertIsNotNone(op.pk)
        self.assertIsNotNone(op.source)
        self.assertTrue(op.destination.is_world)

        transactions = op.get_all_transactions()
        self.assertEqual(transactions.count(), 2)

        self.assertTrue(
            transactions.filter(
                type=TransactionType.CAPITAL_WITHDRAWAL_ISSUANCE
            ).exists(),
            "Issuance transaction should be created",
        )
        self.assertTrue(
            transactions.filter(
                type=TransactionType.CAPITAL_WITHDRAWAL_PAYMENT
            ).exists(),
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

        expected_source = self.withdrawer_entity
        expected_target = self.world_entity

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

    def test_source_must_be_person_entity(self):
        op = self._make_op(source=self.world_entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_must_be_world_entity(self):
        project_entity = Entity.create(EntityType.PROJECT, name="Test Project")

        op = self._make_op(destination=project_entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_entity_must_be_active(self):
        self.withdrawer_entity.active = False
        self.withdrawer_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_entity_must_be_active(self):
        self.world_entity.active = False
        self.world_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_fund_must_be_active(self):
        self.withdrawer_entity.active = False
        self.withdrawer_entity.save()

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
        other_person = Entity.create(EntityType.PERSON, name="Other Source Person")
        # Give the other person funds so the change itself isn't blocked by balance
        self._inject(Decimal("1000.00"))
        op = self._make_op()
        op.save()

        op.source = other_person
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_is_immutable(self):
        other_person = Entity.create(EntityType.PERSON, name="Other Dest Person")
        op = self._make_op()
        op.save()

        op.destination = other_person
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
    # Balance estimation
    # ------------------------------------------------------------------

    def test_withdrawer_balance_decreases_after_withdrawal(self):
        balance_before = self.withdrawer_entity.balance

        op = self._make_op(amount=Decimal("500.00"))
        op.save()

        self.assertEqual(
            self.withdrawer_entity.balance,
            balance_before - Decimal("500.00"),
        )

    # ------------------------------------------------------------------
    # Injection then withdrawal (good path)
    # ------------------------------------------------------------------

    def test_injection_then_withdrawal_succeeds(self):
        # Inject a specific known amount on top of setUp injection
        self._inject(Decimal("300.00"))
        balance_before = self.withdrawer_entity.balance

        op = self._make_op(amount=Decimal("300.00"))
        op.save()  # should not raise

        self.assertIsNotNone(op.pk)
        self.assertEqual(
            self.withdrawer_entity.balance,
            balance_before - Decimal("300.00"),
        )

    # ------------------------------------------------------------------
    # check_balance_on_payment
    # ------------------------------------------------------------------

    def test_check_balance_on_payment_is_enabled(self):
        """Balance is checked before each payment transaction is created."""
        self.assertTrue(CashWithdrawalOperation.check_balance_on_payment)

    def test_insufficient_funds_blocked(self):
        """check_balance_on_payment=True: clean() enforces balance at creation time."""
        broke_person = Entity.create(EntityType.PERSON, name="Broke Person")
        broke_entity = broke_person
        op = self._make_op(source=broke_entity, amount=Decimal("1.00"))
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # No funds → error
    # ------------------------------------------------------------------

    def test_withdrawal_without_sufficient_funds_raises_error(self):
        # Fresh person with zero balance
        broke_person = Entity.create(EntityType.PERSON, name="Broke Person")
        broke_entity = broke_person

        op = self._make_op(source=broke_entity, amount=Decimal("100.00"))
        with self.assertRaises(ValidationError):
            op.save()

    def test_withdrawal_exceeding_balance_raises_error(self):
        balance = self.withdrawer_entity.balance  # 2000.00 from setUp

        op = self._make_op(amount=balance + Decimal("1.00"))
        with self.assertRaises(ValidationError):
            op.save()
