from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import (
    CashInjectionOperation,
    ProjectFundingOperation,
    ProjectRefundOperation,
)
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


def _make_officer(username="officer"):
    return User.objects.create_user(
        username=username, password="testpass", is_staff=True
    )


def _make_project(name="Test Project"):
    return Entity.create(EntityType.PROJECT, name=name)


class ProjectRefundCreateTest(TestCase):
    def setUp(self):
        self.world_entity = Entity.create(EntityType.WORLD)
        self.officer = _make_officer()

        # Shareholder / funder
        shareholder_person = Entity.create(EntityType.PERSON, name="Shareholder Person")
        self.shareholder_entity = shareholder_person

        # Project
        self.project_entity = _make_project()

        # Register shareholder in project
        Stakeholder(
            parent=self.project_entity,
            target=self.shareholder_entity,
            role=StakeholderRole.SHAREHOLDER,
        ).save()

        # Give shareholder funds, then fund the project so it has a balance to refund
        self._inject_to(self.shareholder_entity, Decimal("2000.00"))
        self._fund_project(Decimal("1500.00"))

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

    def _fund_project(self, amount):
        ProjectFundingOperation(
            source=self.shareholder_entity,
            destination=self.project_entity,
            amount=amount,
            operation_type=OperationType.PROJECT_FUNDING,
            date=date.today(),
            description="Setup funding",
            officer=self.officer,
        ).save()

    def _make_op(self, **kwargs):
        defaults = dict(
            source=self.project_entity,
            destination=self.shareholder_entity,
            amount=Decimal("500.00"),
            operation_type=OperationType.PROJECT_REFUND,
            date=date.today(),
            description="Test project refund",
            officer=self.officer,
        )
        defaults.update(kwargs)
        return ProjectRefundOperation(**defaults)

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_creates_issuance_and_payment_transactions(self):
        op = self._make_op()
        op.save()

        self.assertIsNotNone(op.pk)
        self.assertIsNotNone(op.source)
        self.assertIsNotNone(op.destination)

        transactions = op.get_all_transactions()
        self.assertEqual(transactions.count(), 2)

        self.assertTrue(
            transactions.filter(type=TransactionType.PROJECT_REFUND_ISSUANCE).exists(),
            "Issuance transaction should be created",
        )
        self.assertTrue(
            transactions.filter(type=TransactionType.PROJECT_REFUND_PAYMENT).exists(),
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
            self.assertEqual(tx.source, self.project_entity)
            self.assertEqual(tx.target, self.shareholder_entity)

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

    def test_source_must_be_project_entity(self):
        other_person = Entity.create(EntityType.PERSON, name="Wrong Source")
        op = self._make_op(source=other_person)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_must_be_person_entity(self):
        other_project = _make_project("Other Project")
        op = self._make_op(destination=other_project)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_must_be_shareholder_of_source_project(self):
        non_shareholder = Entity.create(EntityType.PERSON, name="Non Shareholder")
        self._inject_to(non_shareholder, Decimal("2000.00"))
        # Fund via project funding so the cap check is also covered
        Stakeholder(
            parent=self.project_entity,
            target=non_shareholder,
            role=StakeholderRole.SHAREHOLDER,
        ).save()
        self._fund_project_from(non_shareholder, Decimal("500.00"))
        # Now remove the stakeholder relationship
        sh = self.project_entity.stakeholders.get(target=non_shareholder)
        sh.active = False
        sh.save()

        op = self._make_op(destination=non_shareholder)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_entity_must_be_active(self):
        self.project_entity.active = False
        self.project_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_entity_must_be_active(self):
        self.shareholder_entity.active = False
        self.shareholder_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_fund_must_be_active(self):
        self.project_entity.active = False
        self.project_entity.save()

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

    def test_amount_exceeding_project_balance_raises_error(self):
        project_balance = self.project_entity.balance  # 1500.00 from setUp

        op = self._make_op(amount=project_balance + Decimal("1.00"))
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_exceeding_shareholder_funded_amount_raises_error(self):
        # Shareholder funded 1500; try refunding more than that
        op = self._make_op(amount=Decimal("1501.00"))
        with self.assertRaises(ValidationError):
            op.save()

    def test_partial_refund_then_second_refund_exceeding_net_raises_error(self):
        # First refund 1000
        self._make_op(amount=Decimal("1000.00")).save()
        # Net remaining refundable = 1500 - 1000 = 500; try refunding 501
        op = self._make_op(amount=Decimal("501.00"))
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_equal_to_funded_amount_succeeds(self):
        # Full refund of the 1500 funded
        op = self._make_op(amount=Decimal("1500.00"))
        op.save()
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
        other_project = _make_project("Other Project")
        op = self._make_op()
        op.save()

        op.source = other_project
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
                officer=self.officer,
                date=date.today(),
            )

    # ------------------------------------------------------------------
    # Balance
    # ------------------------------------------------------------------

    def test_project_fund_decreases_after_refund(self):
        balance_before = self.project_entity.balance

        op = self._make_op(amount=Decimal("600.00"))
        op.save()

        self.assertEqual(
            self.project_entity.balance,
            balance_before - Decimal("600.00"),
        )

    def test_shareholder_fund_increases_after_refund(self):
        balance_before = self.shareholder_entity.balance

        op = self._make_op(amount=Decimal("600.00"))
        op.save()

        self.assertEqual(
            self.shareholder_entity.balance,
            balance_before + Decimal("600.00"),
        )

    # ------------------------------------------------------------------
    # check_balance_on_payment
    # ------------------------------------------------------------------

    def test_check_balance_on_payment_is_disabled(self):
        """Balance is enforced by clean() at creation; no per-payment gate needed."""
        self.assertFalse(ProjectRefundOperation.check_balance_on_payment)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fund_project_from(self, entity, amount):
        ProjectFundingOperation(
            source=entity,
            destination=self.project_entity,
            amount=amount,
            operation_type=OperationType.PROJECT_FUNDING,
            date=date.today(),
            description="Setup funding",
            officer=self.officer,
        ).save()


class ProjectRefundReversalTest(TestCase):
    def setUp(self):
        self.world_entity = Entity.create(EntityType.WORLD)
        self.officer = _make_officer()

        shareholder_person = Entity.create(EntityType.PERSON, name="Shareholder Person")
        self.shareholder_entity = shareholder_person

        self.project_entity = _make_project()

        Stakeholder(
            parent=self.project_entity,
            target=self.shareholder_entity,
            role=StakeholderRole.SHAREHOLDER,
        ).save()

        # Fund shareholder → fund project → create the refund op to reverse
        CashInjectionOperation(
            source=self.world_entity,
            destination=self.shareholder_entity,
            amount=Decimal("2000.00"),
            operation_type=OperationType.CASH_INJECTION,
            date=date.today(),
            description="Setup injection",
            officer=self.officer,
        ).save()

        ProjectFundingOperation(
            source=self.shareholder_entity,
            destination=self.project_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.PROJECT_FUNDING,
            date=date.today(),
            description="Setup funding",
            officer=self.officer,
        ).save()

        self.op = ProjectRefundOperation(
            source=self.project_entity,
            destination=self.shareholder_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.PROJECT_REFUND,
            date=date.today(),
            description="Test project refund",
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
        self.assertEqual(original_txs.count(), 4)  # 2 original + 2 counter

        reversal_txs = reversal.get_all_transactions()
        self.assertEqual(reversal_txs.count(), 0)

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
        balance_after_refund = self.project_entity.balance
        self.op.reverse(officer=self.officer)

        self.assertEqual(
            self.project_entity.balance,
            balance_after_refund + self.op.amount,
        )

    def test_shareholder_fund_restored_after_reversal(self):
        balance_after_refund = self.shareholder_entity.balance
        self.op.reverse(officer=self.officer)

        self.assertEqual(
            self.shareholder_entity.balance,
            balance_after_refund - self.op.amount,
        )
