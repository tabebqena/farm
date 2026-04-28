"""
Comprehensive tests for app_transaction Transaction model.
Tests transaction properties, immutability, validation, and reversal.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import (
    CapitalGainOperation,
    PurchaseOperation,
    CashInjectionOperation,
)
from apps.app_transaction.models import Transaction
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


# =============================================================================
# Fixtures / Helpers
# =============================================================================


def _make_officer(username="officer"):
    return User.objects.create_user(
        username=username, email=f"{username}@test.com", password="pass", is_staff=True
    )


def _make_entity(name, entity_type=EntityType.PERSON, is_vendor=False):
    return Entity.create(entity_type, name=name, is_vendor=is_vendor)


def _make_vendor_stakeholder(project, vendor):
    """Create vendor stakeholder relationship"""
    sh = Stakeholder(
        parent=project,
        target=vendor,
        role=StakeholderRole.VENDOR,
        active=True,
    )
    sh.save()
    return sh


def _get_or_create_system():
    """Get or create system entity"""
    try:
        return Entity.objects.get(entity_type=EntityType.SYSTEM)
    except Entity.DoesNotExist:
        return Entity.create(EntityType.SYSTEM)


def _inject_funds(entity, amount, officer):
    """Add funds to entity via CapitalGainOperation"""
    system = _get_or_create_system()
    CapitalGainOperation(
        source=system,
        destination=entity,
        amount=amount,
        operation_type=OperationType.CAPITAL_GAIN,
        date=timezone.now().date(),
        description="Fund injection",
        officer=officer,
    ).save()


# =============================================================================
# Transaction Auto-Creation Tests (via Operations)
# =============================================================================


class TransactionAutoCreationTests(TestCase):
    """Test Transaction auto-creation through operations"""

    def setUp(self):
        self.officer = _make_officer()
        self.system = _get_or_create_system()
        self.entity_a = _make_entity("Entity A", EntityType.PROJECT)
        self.entity_b = _make_entity("Entity B", EntityType.PERSON, is_vendor=True)
        _make_vendor_stakeholder(self.entity_a, self.entity_b)
        _inject_funds(self.entity_a, Decimal("5000"), self.officer)

    def test_capital_gain_creates_issuance_transaction(self):
        """CapitalGainOperation should auto-create transaction(s)"""
        operation = CapitalGainOperation.objects.create(
            source=self.system,
            destination=self.entity_a,
            amount=Decimal("1000"),
            operation_type=OperationType.CAPITAL_GAIN,
            date=timezone.now().date(),
            officer=self.officer,
            description="Test injection",
        )

        # Should have auto-created at least one transaction
        txs = Transaction.objects.filter(object_id=operation.pk)
        self.assertGreaterEqual(txs.count(), 1)
        # At least one should have the right amount
        amounts = txs.values_list("amount", flat=True)
        self.assertIn(Decimal("1000"), amounts)

    def test_cash_injection_creates_payment_transaction(self):
        """CashInjectionOperation should auto-create transaction"""
        # CashInjection requires World entity as source and Person as destination
        try:
            world = Entity.objects.get(entity_type=EntityType.WORLD)
        except Entity.DoesNotExist:
            world = Entity.create(EntityType.WORLD)

        person = _make_entity("Person", EntityType.PERSON)

        operation = CashInjectionOperation.objects.create(
            source=world,
            destination=person,
            amount=Decimal("500"),
            operation_type=OperationType.CASH_INJECTION,
            date=timezone.now().date(),
            officer=self.officer,
            description="Test injection",
        )

        txs = Transaction.objects.filter(object_id=operation.pk)
        self.assertGreater(txs.count(), 0)

    def test_purchase_creates_issuance_transaction(self):
        """PurchaseOperation should auto-create issuance transaction"""
        operation = PurchaseOperation.objects.create(
            source=self.entity_a,
            destination=self.entity_b,
            amount=Decimal("1000"),
            operation_type=OperationType.PURCHASE,
            date=timezone.now().date(),
            officer=self.officer,
            description="Test purchase",
        )

        # Should have auto-created issuance transaction
        txs = Transaction.objects.filter(object_id=operation.pk)
        self.assertGreater(txs.count(), 0)


# =============================================================================
# Transaction Properties Tests
# =============================================================================


class TransactionPropertiesTests(TestCase):
    """Test Transaction computed properties and fields"""

    def setUp(self):
        self.officer = _make_officer()
        self.system = _get_or_create_system()
        self.entity_a = _make_entity("Entity A", EntityType.PROJECT)

        # Create an operation that generates a transaction
        self.operation = CapitalGainOperation.objects.create(
            source=self.system,
            destination=self.entity_a,
            amount=Decimal("1000"),
            operation_type=OperationType.CAPITAL_GAIN,
            date=timezone.now().date(),
            officer=self.officer,
            description="Test",
        )
        # Get the first transaction created
        self.tx = Transaction.objects.filter(object_id=self.operation.pk).first()
        self.assertIsNotNone(self.tx, "No transaction created for operation")

    def test_is_reversal_false_for_new_transaction(self):
        """is_reversal should be False for new transactions"""
        self.assertFalse(self.tx.is_reversal)

    def test_is_reversed_false_for_new_transaction(self):
        """is_reversed should be False for new transactions"""
        self.assertFalse(self.tx.is_reversed)

    def test_owner_property(self):
        """owner property should return the related document"""
        self.assertEqual(self.tx.owner, self.operation)

    def test_transaction_has_description(self):
        """Transaction should have a description"""
        self.assertIsNotNone(self.tx.description)
        self.assertTrue(len(self.tx.description) > 0)

    def test_transaction_has_date(self):
        """Transaction should have a date"""
        self.assertIsNotNone(self.tx.date)

    def test_transaction_source_target_different(self):
        """Transaction source and target should be different"""
        self.assertNotEqual(self.tx.source, self.tx.target)

    def test_transaction_amount_positive(self):
        """Transaction amount should be positive"""
        self.assertGreater(self.tx.amount, 0)


# =============================================================================
# Transaction Immutability Tests
# =============================================================================


class TransactionImmutabilityTests(TestCase):
    """Test ImmutableMixin prevents changing critical transaction fields"""

    def setUp(self):
        self.officer = _make_officer()
        self.system = _get_or_create_system()
        self.entity_a = _make_entity("Entity A", EntityType.PROJECT)
        self.entity_b = _make_entity("Entity B", EntityType.PERSON)

        self.operation = CapitalGainOperation.objects.create(
            source=self.system,
            destination=self.entity_a,
            amount=Decimal("1000"),
            operation_type=OperationType.CAPITAL_GAIN,
            date=timezone.now().date(),
            officer=self.officer,
            description="Test",
        )
        self.tx = Transaction.objects.filter(object_id=self.operation.pk).first()
        self.assertIsNotNone(self.tx)

    def test_cannot_change_source(self):
        """Should not be able to change transaction source after creation"""
        self.tx.source = self.entity_b
        with self.assertRaises(ValidationError):
            self.tx.save()

    def test_cannot_change_target(self):
        """Should not be able to change transaction target after creation"""
        self.tx.target = self.entity_b
        with self.assertRaises(ValidationError):
            self.tx.save()

    def test_cannot_change_type(self):
        """Should not be able to change transaction type after creation"""
        original_type = self.tx.type
        # Try to change to a different type
        self.tx.type = TransactionType.PURCHASE_PAYMENT
        with self.assertRaises(ValidationError):
            self.tx.save()

    def test_cannot_change_amount(self):
        """Should not be able to change transaction amount after creation"""
        original_amount = self.tx.amount
        self.tx.amount = Decimal("2000")
        with self.assertRaises(ValidationError):
            self.tx.save()

    def test_cannot_change_officer(self):
        """Should not be able to change transaction officer after creation"""
        other_officer = User.objects.create_user(
            username="other", email="other@test.com", password="pass", is_staff=True
        )
        self.tx.officer = other_officer
        with self.assertRaises(ValidationError):
            self.tx.save()

    def test_can_change_note(self):
        """Should be able to change note (not immutable)"""
        self.tx.note = "Updated note"
        self.tx.save()  # Should not raise
        self.tx.refresh_from_db()
        self.assertEqual(self.tx.note, "Updated note")

    def test_can_change_description(self):
        """Should be able to change description (not immutable)"""
        self.tx.description = "Updated description"
        self.tx.save()  # Should not raise
        self.tx.refresh_from_db()
        self.assertEqual(self.tx.description, "Updated description")


# =============================================================================
# Transaction Validation Tests
# =============================================================================


class TransactionValidationTests(TestCase):
    """Test Transaction.clean() validation"""

    def setUp(self):
        self.officer = _make_officer()
        self.system = _get_or_create_system()
        self.entity_a = _make_entity("Entity A", EntityType.PROJECT)

    def test_clean_rejects_same_source_target(self):
        """clean() should reject when source equals target"""
        tx = Transaction(
            source=self.entity_a,
            target=self.entity_a,  # Same!
            type=TransactionType.CAPITAL_GAIN_ISSUANCE,
            amount=Decimal("1000"),
            officer=self.officer,
            description="Test",
            content_type=ContentType.objects.get_for_model(self.entity_a),
            object_id=self.entity_a.pk,
        )

        with self.assertRaises(ValidationError) as ctx:
            tx.clean()

        self.assertIn("different", str(ctx.exception).lower())

    def test_clean_accepts_different_source_target(self):
        """clean() should accept different source and target"""
        entity_b = _make_entity("Entity B", EntityType.PERSON)

        tx = Transaction(
            source=self.entity_a,
            target=entity_b,
            type=TransactionType.CAPITAL_GAIN_ISSUANCE,
            amount=Decimal("1000"),
            officer=self.officer,
            description="Test",
            content_type=ContentType.objects.get_for_model(self.entity_a),
            object_id=self.entity_a.pk,
        )

        # Should not raise
        tx.clean()


# =============================================================================
# Transaction Reversal Tests
# =============================================================================


class TransactionReversalTests(TestCase):
    """Test Transaction.reverse() method"""

    def setUp(self):
        self.officer = _make_officer()
        self.system = _get_or_create_system()
        self.entity_a = _make_entity("Entity A", EntityType.PROJECT)

        self.operation = CapitalGainOperation.objects.create(
            source=self.system,
            destination=self.entity_a,
            amount=Decimal("1000"),
            operation_type=OperationType.CAPITAL_GAIN,
            date=timezone.now().date(),
            officer=self.officer,
            description="Test",
        )
        self.tx = Transaction.objects.filter(object_id=self.operation.pk).first()
        self.assertIsNotNone(self.tx)

    def test_reverse_creates_reversal_transaction(self):
        """reverse() should create a reversal transaction"""
        reversal = self.tx.reverse(officer=self.officer)

        self.assertIsNotNone(reversal.pk)
        self.assertEqual(reversal.reversal_of, self.tx)
        self.assertTrue(reversal.is_reversal)

    def test_reversal_swaps_source_and_target(self):
        """Reversal should have source and target swapped"""
        reversal = self.tx.reverse(officer=self.officer)

        self.assertEqual(reversal.source, self.tx.target)
        self.assertEqual(reversal.target, self.tx.source)

    def test_reversal_has_same_amount(self):
        """Reversal should have same amount as original"""
        reversal = self.tx.reverse(officer=self.officer)

        self.assertEqual(reversal.amount, self.tx.amount)

    def test_reversal_has_same_type(self):
        """Reversal should have same transaction type"""
        reversal = self.tx.reverse(officer=self.officer)

        self.assertEqual(reversal.type, self.tx.type)

    def test_original_marked_as_reversed(self):
        """Original transaction should be marked as reversed"""
        reversal = self.tx.reverse(officer=self.officer)

        self.tx.refresh_from_db()
        self.assertTrue(self.tx.is_reversed)

    def test_cannot_reverse_already_reversed_transaction(self):
        """Cannot reverse a transaction that's already reversed"""
        reversal1 = self.tx.reverse(officer=self.officer)

        # Try to reverse again
        with self.assertRaises(ValidationError):
            self.tx.reverse(officer=self.officer)

    def test_cannot_reverse_a_reversal(self):
        """Cannot reverse a reversal transaction"""
        reversal = self.tx.reverse(officer=self.officer)

        # Try to reverse the reversal
        with self.assertRaises(ValidationError):
            reversal.reverse(officer=self.officer)

    def test_reverse_with_custom_date(self):
        """reverse() should respect custom date parameter"""
        custom_date = timezone.now() - timedelta(days=5)
        reversal = self.tx.reverse(officer=self.officer, date=custom_date)

        # Date should be within a second of our custom date
        delta = abs((reversal.date - custom_date).total_seconds())
        self.assertLess(delta, 1.0)

    def test_reverse_with_reason(self):
        """reverse() should include reason in description"""
        reason = "Testing reversal"
        reversal = self.tx.reverse(officer=self.officer, reason=reason)

        self.assertIn(reason, reversal.description)


# =============================================================================
# Transaction GenericForeignKey Tests
# =============================================================================


class TransactionGenericForeignKeyTests(TestCase):
    """Test Transaction's GenericForeignKey document field"""

    def setUp(self):
        self.officer = _make_officer()
        self.system = _get_or_create_system()
        self.entity_a = _make_entity("Entity A", EntityType.PROJECT)

        self.operation = CapitalGainOperation.objects.create(
            source=self.system,
            destination=self.entity_a,
            amount=Decimal("1000"),
            operation_type=OperationType.CAPITAL_GAIN,
            date=timezone.now().date(),
            officer=self.officer,
            description="Test",
        )

    def test_document_returns_related_object(self):
        """document GenericForeignKey should return the related operation"""
        tx = Transaction.objects.filter(object_id=self.operation.pk).first()
        self.assertIsNotNone(tx)

        # The document should resolve to the operation
        self.assertEqual(tx.document.pk, self.operation.pk)

    def test_transaction_links_to_correct_content_type(self):
        """Transaction should link to correct ContentType"""
        tx = Transaction.objects.filter(object_id=self.operation.pk).first()
        self.assertIsNotNone(tx)
        expected_ct = ContentType.objects.get_for_model(CapitalGainOperation)

        self.assertEqual(tx.content_type, expected_ct)

    def test_transaction_links_to_correct_object_id(self):
        """Transaction should link to correct object_id"""
        tx = Transaction.objects.filter(object_id=self.operation.pk).first()
        self.assertIsNotNone(tx)

        self.assertEqual(tx.object_id, self.operation.pk)

    def test_transaction_owner_is_document(self):
        """owner property should return the document"""
        tx = Transaction.objects.filter(object_id=self.operation.pk).first()
        self.assertIsNotNone(tx)

        self.assertEqual(tx.owner, self.operation)
