from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from apps.app_entity.models import Entity, EntityType
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CapitalGainOperation, ExpenseOperation
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_officer(username="officer"):
    return User.objects.create_user(
        username=username, password="testpass", is_staff=True
    )


def _make_person_entity(name):
    person = Entity.create(EntityType.PERSON, name=name)
    return person


def _make_project_entity(name):
    project = Entity.create(EntityType.PROJECT, name=name)
    project.save()
    return project


def _make_world_entity():
    return Entity.create(EntityType.WORLD)


def _inject_project(system_entity, dest_entity, amount, officer_user):
    """Seed a Project entity's fund via CapitalGain."""
    CapitalGainOperation(
        source=system_entity,
        destination=dest_entity,
        amount=amount,
        operation_type=OperationType.CAPITAL_GAIN,
        date=date.today(),
        description="Seed project balance",
        officer=officer_user,
    ).save()


def _make_expense_category(parent_entity, name="Veterinary Consultation"):
    from apps.app_entity.models.category import FinancialCategoriesEntitiesRelations, FinancialCategory


    cat, _ = FinancialCategory.objects.get_or_create(
        name=name,
        defaults={"category_type": "EXPENSE", "is_active": True},
    )
    FinancialCategoriesEntitiesRelations.objects.get_or_create(
        entity=parent_entity, category=cat, defaults={"max_limit": Decimal("0.00")}
    )
    return cat


# ---------------------------------------------------------------------------
# ExpenseCreateTest
# ---------------------------------------------------------------------------


class ExpenseCreateTest(TestCase):
    """
    Tests for expense operation creation: validation, issuance transaction, and
    fund behaviour.

    On save, only an EXPENSE_ISSUANCE transaction is created (obligation record).
    EXPENSE_ISSUANCE is a non-cash transaction — it does NOT affect fund balances.
    Cash movement only happens later via create_payment_transaction().
    """

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.world_entity = _make_world_entity()
        self.officer_user = _make_officer()

        self.project_entity = _make_project_entity("Test Farm Project")
        _inject_project(
            self.system_entity,
            self.project_entity,
            Decimal("5000.00"),
            self.officer_user,
        )

    def _make_op(self, **kwargs):
        defaults = dict(
            source=self.project_entity,
            destination=self.world_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.EXPENSE,
            date=date.today(),
            description="Test expense",
            officer=self.officer_user,
        )
        defaults.update(kwargs)
        return ExpenseOperation(**defaults)

    # ------------------------------------------------------------------
    # Happy path — issuance only on creation
    # ------------------------------------------------------------------

    def test_save_creates_exactly_one_issuance_transaction(self):
        op = self._make_op()
        op.save()

        transactions = op.get_all_transactions()
        self.assertEqual(transactions.count(), 1)
        self.assertTrue(
            transactions.filter(type=TransactionType.EXPENSE_ISSUANCE).exists(),
            "Issuance transaction must be created on save",
        )

    def test_no_payment_transaction_created_on_save(self):
        op = self._make_op()
        op.save()

        self.assertFalse(
            op.get_all_transactions()
            .filter(type=TransactionType.EXPENSE_PAYMENT)
            .exists(),
            "Payment transaction must NOT be created on save — expense is not one-shot",
        )

    def test_issuance_transaction_direction_is_project_to_world(self):
        op = self._make_op()
        op.save()

        tx = op.get_all_transactions().get(type=TransactionType.EXPENSE_ISSUANCE)
        self.assertEqual(tx.source, self.project_entity)
        self.assertEqual(tx.target, self.world_entity)

    def test_issuance_transaction_amount_matches_operation(self):
        op = self._make_op(amount=Decimal("750.00"))
        op.save()

        tx = op.get_all_transactions().get(type=TransactionType.EXPENSE_ISSUANCE)
        self.assertEqual(tx.amount, Decimal("750.00"))

    def test_project_fund_balance_unchanged_after_save(self):
        """EXPENSE_ISSUANCE is non-cash; it does not affect fund balances."""
        balance_before = self.project_entity.balance

        op = self._make_op(amount=Decimal("800.00"))
        op.save()

        self.project_entity.refresh_from_db()
        self.assertEqual(self.project_entity.balance, balance_before)

    def test_amount_remaining_to_settle_equals_full_amount_after_creation(self):
        op = self._make_op(amount=Decimal("1200.00"))
        op.save()

        self.assertEqual(op.amount_remaining_to_settle, Decimal("1200.00"))

    def test_is_not_fully_settled_after_creation(self):
        op = self._make_op()
        op.save()

        self.assertFalse(op.is_fully_settled)

    # ------------------------------------------------------------------
    # Category config
    # ------------------------------------------------------------------

    def test_has_category_config_is_true(self):
        self.assertTrue(ExpenseOperation.has_category)

    def test_category_required_config_is_true(self):
        self.assertTrue(ExpenseOperation.category_required)

    def test_expense_category_can_be_created_with_expense_type(self):
        from apps.app_entity.models.category import FinancialCategoriesEntitiesRelations, FinancialCategory

        cat = _make_expense_category(self.project_entity)

        self.assertEqual(cat.category_type, "EXPENSE")
        # Verify the relation exists
        from apps.app_operation.models.period import (
            
        )

        self.assertTrue(
            FinancialCategoriesEntitiesRelations.objects.filter(
                entity=self.project_entity, category=cat
            ).exists()
        )

    def test_non_expense_category_type_is_distinct_from_expense(self):
        from apps.app_entity.models.category import FinancialCategoriesEntitiesRelations, FinancialCategory

        
        income_cat = FinancialCategory.objects.create(
            name="Animal Sale Income",
            category_type="INCOME",
        )
        FinancialCategoriesEntitiesRelations.objects.create(
            entity=self.project_entity, category=income_cat
        )
        self.assertNotEqual(income_cat.category_type, "EXPENSE")

    # ------------------------------------------------------------------
    # Source validation
    # ------------------------------------------------------------------

    def test_source_must_be_a_project_entity(self):
        non_project = _make_person_entity("Not A Project")
        op = self._make_op(source=non_project)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_must_be_active(self):
        self.project_entity.active = False
        self.project_entity.save()

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
    # Destination validation
    # ------------------------------------------------------------------

    def test_destination_must_be_world_entity(self):
        non_world = _make_project_entity("Not The World")
        op = self._make_op(destination=non_world)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_person_entity_raises_validation_error(self):
        person = _make_person_entity("Some Person")
        op = self._make_op(destination=person)
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
        op = self._make_op(amount=Decimal("-500.00"))
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

    def test_source_is_immutable_after_save(self):
        op = self._make_op()
        op.save()

        other_project = _make_project_entity("Other Project")
        op.source = other_project
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_is_immutable_after_save(self):
        op = self._make_op()
        op.save()

        # Can't have two world entities, so use a person as the "other" destination
        other_dest = _make_person_entity("Other Destination")
        op.destination = other_dest
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_is_immutable_after_save(self):
        op = self._make_op()
        op.save()

        op.amount = Decimal("9999.00")
        with self.assertRaises(ValidationError):
            op.save()


# ---------------------------------------------------------------------------
# ExpensePaymentTest
# ---------------------------------------------------------------------------
