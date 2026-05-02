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
)
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()



class ProjectFundingCreateTest(TestCase):
    def setUp(self):
        self.world_entity = Entity.create(EntityType.WORLD)

        self.officer = User.objects.create_user(
            username="officer", password="testpass", is_staff=True
        )

        # Funder: person entity
        funder_person = Entity.create(
            EntityType.PERSON, name="Funder Person", is_shareholder=True
        )
        self.funder_entity = funder_person

        # Project entity
        self.project_entity = Entity.create(EntityType.PROJECT, name="Test Project")

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
        self.assertIsNotNone(op.source)
        self.assertIsNotNone(op.destination)

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
            self.assertEqual(tx.source, self.funder_entity)
            self.assertEqual(tx.target, self.project_entity)

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
        non_person = Entity.create(EntityType.PROJECT, name="Another Project")
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
        non_shareholder_person = Entity.create(
            EntityType.PERSON, name="Non Shareholder"
        )
        self._inject_to(non_shareholder_person, Decimal("1000.00"))

        op = self._make_op(source=non_shareholder_person)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_must_be_project_entity(self):
        other_person = Entity.create(EntityType.PERSON, name="Wrong Destination")
        op = self._make_op(destination=other_person)
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
        self.funder_entity.active = False
        self.funder_entity.save()

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
        balance = self.funder_entity.balance  # 2000.00 from setUp

        op = self._make_op(amount=balance + Decimal("1.00"))
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_equal_to_funder_balance_succeeds(self):
        balance = self.funder_entity.balance  # 2000.00 from setUp

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
        other_funder = Entity.create(EntityType.PERSON, name="Other Funder")
        Stakeholder(
            parent=self.project_entity,
            target=other_funder,
            role=StakeholderRole.SHAREHOLDER,
        ).save()
        self._inject_to(other_funder, Decimal("1000.00"))

        op = self._make_op()
        op.save()

        op.source = other_funder
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_is_immutable(self):
        other_project_entity = Entity.create(EntityType.PROJECT, name="Other Project")

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
        balance_before = self.project_entity.balance

        op = self._make_op(amount=Decimal("700.00"))
        op.save()

        self.assertEqual(
            self.project_entity.balance,
            balance_before + Decimal("700.00"),
        )

    def test_funder_fund_decreases_after_funding(self):
        balance_before = self.funder_entity.balance

        op = self._make_op(amount=Decimal("700.00"))
        op.save()

        self.assertEqual(
            self.funder_entity.balance,
            balance_before - Decimal("700.00"),
        )

    # ------------------------------------------------------------------
    # check_balance_on_payment
    # ------------------------------------------------------------------

    def test_check_balance_on_payment_is_disabled(self):
        """Balance is enforced by clean() at creation; no per-payment gate needed."""
        self.assertFalse(ProjectFundingOperation.check_balance_on_payment)

    # ------------------------------------------------------------------
    # Closed period validation
    # ------------------------------------------------------------------

    def test_operation_blocked_when_destination_in_closed_period(self):
        """Regression: validate destination entity's period, not just source's."""
        from apps.app_operation.models.period import FinancialPeriod
        from datetime import timedelta

        # Create a closed period for the project
        today = date.today()
        closed_period = FinancialPeriod.objects.create(
            entity=self.project_entity,
            start_date=today - timedelta(days=10),
            end_date=today - timedelta(days=1),  # Closed: end_date is in the past
        )

        # Shareholder's period is open (no period, so will be assigned to an open one)
        # Try to fund the project from the shareholder
        op = self._make_op(date=today - timedelta(days=5))

        # Should fail because the project is in a closed period
        with self.assertRaises(ValidationError):
            op.save()

    def test_operation_blocked_when_source_in_closed_period(self):
        """Validate source entity's period too."""
        from apps.app_operation.models.period import FinancialPeriod
        from datetime import timedelta

        # Create a closed period for the funder
        today = date.today()
        closed_period = FinancialPeriod.objects.create(
            entity=self.funder_entity,
            start_date=today - timedelta(days=10),
            end_date=today - timedelta(days=1),  # Closed: end_date is in the past
        )

        # Try to fund the project from the shareholder (in closed period)
        op = self._make_op(date=today - timedelta(days=5))

        # Should fail because the funder is in a closed period
        with self.assertRaises(ValidationError):
            op.save()

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
