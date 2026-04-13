from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, Person, Project, Stakeholder, StakeholderRole
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CapitalGainOperation, SaleOperation
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_officer(username="officer"):
    user = User.objects.create_user(
        username=username, password="testpass", is_staff=True
    )
    person = Person.create(private_name=f"Officer {username}", auth_user=user)
    return person.entity


def _make_person_entity(name):
    person = Person.create(private_name=name)
    return person.entity


def _make_project_entity(name):
    project = Project(name=name)
    project.save()
    return Entity.create(owner=project)


def _make_client_entity(name):
    person = Person.create(private_name=name, is_client=True)
    return person.entity


def _inject_project(system_entity, dest_entity, amount, officer_entity):
    """Seed a Project entity's fund via CapitalGain."""
    CapitalGainOperation(
        source=system_entity,
        destination=dest_entity,
        amount=amount,
        operation_type=OperationType.CAPITAL_GAIN,
        date=date.today(),
        description="Seed project balance",
        officer=officer_entity,
    ).save()


def _seed_client_fund(system_entity, client_entity, amount, officer_entity):
    """Seed a Client entity's fund via CapitalGain so collections can deduct from it."""
    CapitalGainOperation(
        source=system_entity,
        destination=client_entity,
        amount=amount,
        operation_type=OperationType.CAPITAL_GAIN,
        date=date.today(),
        description="Seed client balance",
        officer=officer_entity,
    ).save()


def _make_client_stakeholder(project_entity, client_entity, active=True):
    sh = Stakeholder(
        parent=project_entity,
        target=client_entity,
        role=StakeholderRole.CLIENT,
        active=active,
    )
    sh.save()
    return sh


# ---------------------------------------------------------------------------
# SaleCreateTest
# ---------------------------------------------------------------------------


class SaleCreateTest(TestCase):
    """
    Tests for sale operation creation: validation, issuance transaction, and
    fund behaviour.

    On save, only a SALE_ISSUANCE transaction is created (receivable record).
    SALE_ISSUANCE is a non-cash transaction — it does NOT affect fund balances.
    Cash movement only happens later via create_payment_transaction() (collection).
    """

    def setUp(self):
        self.system_entity = Entity.create(is_system=True)
        self.officer_entity = _make_officer()

        self.project_entity = _make_project_entity("Test Farm Project")

        self.client_entity = _make_client_entity("Big Buyer Corp")
        _seed_client_fund(
            self.system_entity,
            self.client_entity,
            Decimal("5000.00"),
            self.officer_entity,
        )
        _make_client_stakeholder(self.project_entity, self.client_entity)

    def _make_op(self, **kwargs):
        defaults = dict(
            source=self.client_entity,
            destination=self.project_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.SALE,
            date=date.today(),
            description="Test sale",
            officer=self.officer_entity,
        )
        defaults.update(kwargs)
        return SaleOperation(**defaults)

    # ------------------------------------------------------------------
    # Happy path — issuance only on creation
    # ------------------------------------------------------------------

    def test_save_creates_exactly_one_issuance_transaction(self):
        op = self._make_op()
        op.save()

        transactions = op.get_all_transactions()
        self.assertEqual(transactions.count(), 1)
        self.assertTrue(
            transactions.filter(type=TransactionType.SALE_ISSUANCE).exists(),
            "Issuance transaction must be created on save",
        )

    def test_no_collection_transaction_created_on_save(self):
        op = self._make_op()
        op.save()

        self.assertFalse(
            op.get_all_transactions()
            .filter(type=TransactionType.SALE_COLLECTION)
            .exists(),
            "Collection transaction must NOT be created on save — sale is not one-shot",
        )

    def test_issuance_transaction_direction_is_client_to_project(self):
        op = self._make_op()
        op.save()

        tx = op.get_all_transactions().get(type=TransactionType.SALE_ISSUANCE)
        self.assertEqual(tx.source, self.client_entity.fund)
        self.assertEqual(tx.target, self.project_entity.fund)

    def test_issuance_transaction_amount_matches_operation(self):
        op = self._make_op(amount=Decimal("750.00"))
        op.save()

        tx = op.get_all_transactions().get(type=TransactionType.SALE_ISSUANCE)
        self.assertEqual(tx.amount, Decimal("750.00"))

    def test_project_fund_balance_unchanged_after_save(self):
        """SALE_ISSUANCE is non-cash; it does not affect fund balances."""
        balance_before = self.project_entity.fund.balance

        op = self._make_op(amount=Decimal("800.00"))
        op.save()

        self.project_entity.fund.refresh_from_db()
        self.assertEqual(self.project_entity.fund.balance, balance_before)

    def test_client_fund_balance_unchanged_after_save(self):
        """SALE_ISSUANCE is non-cash; it does not affect fund balances."""
        balance_before = self.client_entity.fund.balance

        op = self._make_op(amount=Decimal("800.00"))
        op.save()

        self.client_entity.fund.refresh_from_db()
        self.assertEqual(self.client_entity.fund.balance, balance_before)

    def test_amount_remaining_to_settle_equals_full_amount_after_creation(self):
        op = self._make_op(amount=Decimal("1200.00"))
        op.save()

        self.assertEqual(op.amount_remaining_to_settle, Decimal("1200.00"))

    def test_is_not_fully_settled_after_creation(self):
        op = self._make_op()
        op.save()

        self.assertFalse(op.is_fully_settled)

    # ------------------------------------------------------------------
    # Source validation — must be a client entity
    # ------------------------------------------------------------------

    def test_source_must_be_a_client_entity(self):
        non_client = _make_person_entity("Not A Client")
        op = self._make_op(source=non_client)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_project_entity_raises_validation_error(self):
        other_project = _make_project_entity("Some Project")
        op = self._make_op(source=other_project)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_must_be_active(self):
        self.client_entity.active = False
        self.client_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_fund_must_be_active(self):
        self.client_entity.fund.active = False
        self.client_entity.fund.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Destination validation — must be a project entity
    # ------------------------------------------------------------------

    def test_destination_must_be_a_project_entity(self):
        non_project = _make_person_entity("Not A Project")
        op = self._make_op(destination=non_project)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_must_be_active_stakeholder_project(self):
        unregistered_project = _make_project_entity("Unregistered Project")
        # is a project but no Stakeholder relationship with this client
        op = self._make_op(destination=unregistered_project)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_with_inactive_stakeholder_raises_validation_error(self):
        inactive_project = _make_project_entity("Inactive Relationship Project")
        _make_client_stakeholder(inactive_project, self.client_entity, active=False)

        op = self._make_op(destination=inactive_project)
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

    def test_officer_must_be_a_person_entity(self):
        op = self._make_op(officer=self.system_entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_officer_must_have_auth_user(self):
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

    def test_source_is_immutable_after_save(self):
        op = self._make_op()
        op.save()

        other_client = _make_client_entity("Other Client")
        _make_client_stakeholder(self.project_entity, other_client)
        op.source = other_client
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_is_immutable_after_save(self):
        op = self._make_op()
        op.save()

        other_project = _make_project_entity("Other Project")
        _make_client_stakeholder(other_project, self.client_entity)
        op.destination = other_project
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_is_immutable_after_save(self):
        op = self._make_op()
        op.save()

        op.amount = Decimal("9999.00")
        with self.assertRaises(ValidationError):
            op.save()


# ---------------------------------------------------------------------------
# SaleCollectionTest
# ---------------------------------------------------------------------------


class SaleCollectionTest(TestCase):
    """
    Tests for SALE_COLLECTION transactions.

    The project records a sale receivable on save (SALE_ISSUANCE, non-cash).
    Collections are created explicitly and move funds: client.fund → project.fund.
    Multiple partial collections are allowed, up to the total operation amount.
    """

    def setUp(self):
        self.system_entity = Entity.create(is_system=True)
        self.officer_entity = _make_officer()

        self.project_entity = _make_project_entity("Farm Project")

        self.client_entity = _make_client_entity("Big Buyer Corp")
        _seed_client_fund(
            self.system_entity,
            self.client_entity,
            Decimal("5000.00"),
            self.officer_entity,
        )
        _make_client_stakeholder(self.project_entity, self.client_entity)

        self.op = SaleOperation(
            source=self.client_entity,
            destination=self.project_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.SALE,
            date=date.today(),
            description="Test sale",
            officer=self.officer_entity,
        )
        self.op.save()

    def _collect(self, amount):
        self.op.create_payment_transaction(
            amount=amount,
            officer=self.officer_entity,
            date=date.today(),
        )

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_collection_creates_sale_collection_transaction(self):
        self._collect(Decimal("400.00"))

        collection_txs = self.op.get_all_transactions().filter(
            type=TransactionType.SALE_COLLECTION
        )
        self.assertEqual(collection_txs.count(), 1)

    def test_collection_transaction_direction_is_client_to_project(self):
        self._collect(Decimal("400.00"))

        tx = self.op.get_all_transactions().get(type=TransactionType.SALE_COLLECTION)
        self.assertEqual(tx.source, self.client_entity.fund)
        self.assertEqual(tx.target, self.project_entity.fund)

    def test_amount_remaining_to_settle_decreases_after_collection(self):
        self._collect(Decimal("400.00"))

        self.assertEqual(self.op.amount_remaining_to_settle, Decimal("600.00"))

    def test_multiple_partial_collections_are_allowed(self):
        self._collect(Decimal("300.00"))
        self._collect(Decimal("300.00"))
        self._collect(Decimal("400.00"))

        collection_txs = self.op.get_all_transactions().filter(
            type=TransactionType.SALE_COLLECTION
        )
        self.assertEqual(collection_txs.count(), 3)
        self.assertEqual(self.op.amount_remaining_to_settle, Decimal("0.00"))

    def test_multiple_collections_accumulate_correctly(self):
        self._collect(Decimal("250.00"))
        self._collect(Decimal("350.00"))

        self.assertEqual(self.op.amount_settled, Decimal("600.00"))
        self.assertEqual(self.op.amount_remaining_to_settle, Decimal("400.00"))

    def test_full_collection_marks_operation_as_fully_settled(self):
        self._collect(Decimal("1000.00"))

        self.assertTrue(self.op.is_fully_settled)
        self.assertEqual(self.op.amount_remaining_to_settle, Decimal("0.00"))

    def test_client_fund_decreases_by_collection_amount(self):
        balance_before = self.client_entity.fund.balance

        self._collect(Decimal("600.00"))

        self.client_entity.fund.refresh_from_db()
        self.assertEqual(
            self.client_entity.fund.balance,
            balance_before - Decimal("600.00"),
        )

    def test_project_fund_increases_by_collection_amount(self):
        balance_before = self.project_entity.fund.balance

        self._collect(Decimal("600.00"))

        self.project_entity.fund.refresh_from_db()
        self.assertEqual(
            self.project_entity.fund.balance,
            balance_before + Decimal("600.00"),
        )

    def test_total_transactions_after_partial_collection_is_two(self):
        """One issuance (created on save) + one collection = two transactions."""
        self._collect(Decimal("500.00"))

        self.assertEqual(self.op.get_all_transactions().count(), 2)

    # ------------------------------------------------------------------
    # Over-collection blocked
    # ------------------------------------------------------------------

    def test_collection_exceeding_operation_amount_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._collect(Decimal("1500.00"))

    def test_partial_collection_then_over_collection_raises_validation_error(self):
        self._collect(Decimal("800.00"))

        with self.assertRaises(ValidationError):
            self._collect(Decimal("300.00"))  # only 200 remaining

    def test_zero_collection_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._collect(Decimal("0.00"))

    def test_negative_collection_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._collect(Decimal("-100.00"))


# ---------------------------------------------------------------------------
# SaleReversalTest
# ---------------------------------------------------------------------------


class SaleReversalTest(TestCase):
    """
    Tests for sale operation reversal.

    Reversal is allowed only when no SALE_COLLECTION transactions exist.
    Reversing the operation creates a counter-transaction for the issuance.
    Since SALE_ISSUANCE is non-cash, fund balances are unaffected by reversal.
    """

    def setUp(self):
        self.system_entity = Entity.create(is_system=True)
        self.officer_entity = _make_officer()

        self.project_entity = _make_project_entity("Farm Project")

        self.client_entity = _make_client_entity("Big Buyer Corp")
        _seed_client_fund(
            self.system_entity,
            self.client_entity,
            Decimal("5000.00"),
            self.officer_entity,
        )
        _make_client_stakeholder(self.project_entity, self.client_entity)

        self.op = SaleOperation(
            source=self.client_entity,
            destination=self.project_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.SALE,
            date=date.today(),
            description="Test sale",
            officer=self.officer_entity,
        )
        self.op.save()

    # ------------------------------------------------------------------
    # Happy path — no collections, reversal allowed
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

    def test_reversal_is_marked_as_reversal(self):
        reversal = self.op.reverse(officer=self.officer_entity)

        self.assertTrue(reversal.is_reversal)
        self.assertFalse(reversal.is_reversed)

    def test_reverse_inherits_amount_source_destination(self):
        reversal = self.op.reverse(officer=self.officer_entity)

        self.assertEqual(reversal.amount, self.op.amount)
        self.assertEqual(reversal.source, self.op.source)
        self.assertEqual(reversal.destination, self.op.destination)

    def test_reverse_creates_counter_transaction_for_issuance(self):
        """Only the SALE_ISSUANCE is implicitly reversed (not one-shot operation)."""
        self.op.reverse(officer=self.officer_entity)

        all_txs = self.op.get_all_transactions()
        # 1 original SALE_ISSUANCE + 1 counter-SALE_ISSUANCE
        self.assertEqual(all_txs.count(), 2)

        counter_txs = all_txs.filter(reversal_of__isnull=False)
        self.assertEqual(counter_txs.count(), 1)

    def test_reverse_counter_transaction_flips_funds(self):
        self.op.reverse(officer=self.officer_entity)

        original_tx = self.op.get_all_transactions().get(reversal_of__isnull=True)
        counter_tx = original_tx.reversed_by

        self.assertEqual(counter_tx.source, original_tx.target)
        self.assertEqual(counter_tx.target, original_tx.source)
        self.assertEqual(counter_tx.amount, original_tx.amount)

    def test_fund_balances_unchanged_after_reversal(self):
        """Issuance is non-cash; reversing it leaves all fund balances untouched."""
        project_balance_before = self.project_entity.fund.balance
        client_balance_before = self.client_entity.fund.balance

        self.op.reverse(officer=self.officer_entity)

        self.project_entity.fund.refresh_from_db()
        self.client_entity.fund.refresh_from_db()
        self.assertEqual(self.project_entity.fund.balance, project_balance_before)
        self.assertEqual(self.client_entity.fund.balance, client_balance_before)

    # ------------------------------------------------------------------
    # Reversal blocked by existing collection
    # ------------------------------------------------------------------

    def test_reversal_blocked_when_collection_exists(self):
        self.op.create_payment_transaction(
            amount=Decimal("500.00"),
            officer=self.officer_entity,
            date=date.today(),
        )

        with self.assertRaises(ValidationError):
            self.op.reverse(officer=self.officer_entity)

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


# ---------------------------------------------------------------------------
# SaleBalanceGuardTest
# ---------------------------------------------------------------------------


class SaleBalanceGuardTest(TestCase):
    """
    Tests that check_balance_on_payment=True on SaleOperation is enforced.

    The client fund balance is seeded below the sale amount so the
    over-collection guard never fires; only the fund-balance check matters.
    """

    def setUp(self):
        self.system_entity = Entity.create(is_system=True)
        self.officer_entity = _make_officer()

        self.project_entity = _make_project_entity("Farm Project")

        self.client_entity = _make_client_entity("Low-Balance Client")
        # Seed only 200 — less than the collection amount we will attempt (600),
        # but the sale itself is for 1000 so the over-collection guard would
        # allow 600.  Only check_balance_on_payment can reject it.
        _seed_client_fund(
            self.system_entity,
            self.client_entity,
            Decimal("200.00"),
            self.officer_entity,
        )
        _make_client_stakeholder(self.project_entity, self.client_entity)

        self.op = SaleOperation(
            source=self.client_entity,
            destination=self.project_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.SALE,
            date=date.today(),
            description="Test sale",
            officer=self.officer_entity,
        )
        self.op.save()

    def test_check_balance_on_payment_is_enabled(self):
        """Balance is checked before each collection transaction is created."""
        self.assertTrue(SaleOperation.check_balance_on_payment)

    def test_collection_blocked_when_client_fund_has_insufficient_balance(self):
        """check_balance_on_payment=True: collection is rejected when the client
        fund balance is below the requested payment amount, even though the
        remaining-to-settle allows it."""
        with self.assertRaises(ValidationError):
            self.op.create_payment_transaction(
                amount=Decimal("600.00"),
                officer=self.officer_entity,
                date=date.today(),
            )

    def test_collection_succeeds_when_amount_within_client_fund_balance(self):
        """Partial collection that fits within the available fund balance is allowed."""
        self.op.create_payment_transaction(
            amount=Decimal("150.00"),
            officer=self.officer_entity,
            date=date.today(),
        )
        self.client_entity.fund.refresh_from_db()
        self.assertEqual(self.client_entity.fund.balance, Decimal("50.00"))
