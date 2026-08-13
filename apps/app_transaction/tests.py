"""
Comprehensive tests for app_transaction Transaction model.
Tests transaction properties, immutability, validation, and reversal.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import (
    CapitalGainOperation,
    PurchaseOperation,
    CashInjectionOperation,
    CorrectionCreditOperation,
    WorkerAdvanceOperation,
)
from apps.app_operation.tests.base import assert_tx_types
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


def _make_entity(name, entity_type=EntityType.PERSON, is_vendor=False, is_worker=False):
    return Entity.create(
        entity_type, name=name, is_vendor=is_vendor, is_worker=is_worker
    )


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
    """Add real cash funds to a project entity via CorrectionCreditOperation.

    A CapitalGain is non-cash (its *_PAYMENT is excluded from ``payment_types()``),
    so it cannot fund an entity's spendable balance.
    """
    system = _get_or_create_system()
    CorrectionCreditOperation(
        source=system,
        destination=entity,
        amount=amount,
        operation_type=OperationType.CORRECTION_CREDIT,
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

        # Should have auto-created the exact one-shot issuance + payment pair
        assert_tx_types(
            self,
            operation,
            {
                TransactionType.CAPITAL_GAIN_ISSUANCE: 1,
                TransactionType.CAPITAL_GAIN_PAYMENT: 1,
            },
        )
        amounts = Transaction.objects.filter(
            object_id=operation.pk
        ).values_list("amount", flat=True)
        self.assertEqual(set(amounts), {Decimal("1000")})

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

        assert_tx_types(
            self,
            operation,
            {
                TransactionType.CASH_INJECTION_ISSUANCE: 1,
                TransactionType.CASH_INJECTION_PAYMENT: 1,
            },
        )

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

        # Should have auto-created exactly one issuance transaction (no payment)
        assert_tx_types(self, operation, {TransactionType.PURCHASE_ISSUANCE: 1})


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


# =============================================================================
# Entity Transactions List View Tests (balance tracking)
# =============================================================================


class EntityTransactionsViewTests(TestCase):
    """Test the entity transactions list view used for balance tracking."""

    def setUp(self):
        self.client = Client()
        self.officer = _make_officer()
        self.system = _get_or_create_system()
        self.entity = _make_entity("Balance Project", EntityType.PROJECT)

    def _url(self):
        return reverse(
            "entity_payment_transactions_list", kwargs={"entity_pk": self.entity.pk}
        )

    def _login(self):
        self.client.force_login(self.officer)

    def _inject(self, amount=Decimal("1000.00")):
        """Record an incoming CAPITAL_GAIN_PAYMENT (target of transaction)."""
        _inject_funds(self.entity, amount, self.officer)

    def _outgoing(self, amount=Decimal("200.00")):
        """Record an outgoing PURCHASE_PAYMENT (source of transaction)."""
        vendor = _make_entity("Vendor X", EntityType.PERSON, is_vendor=True)
        _make_vendor_stakeholder(self.entity, vendor)
        op = PurchaseOperation.objects.create(
            source=self.entity,
            destination=vendor,
            amount=amount,
            operation_type=OperationType.PURCHASE,
            date=timezone.now().date(),
            officer=self.officer,
            description="Test purchase",
        )
        op.create_payment_transaction(
            amount=amount,
            officer=self.officer,
            date=timezone.now().date(),
        )

    def test_authorized_user_can_load_entity_transactions(self):
        """Logged-in user can view the entity transactions page."""
        self._login()
        self._inject(Decimal("1000.00"))

        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["entity"], self.entity)
        self.assertEqual(len(response.context["transactions"]), 1)

    def test_navigation_shows_entity_display_name(self):
        """Entity transactions navigation shows the real entity name instead of 'Entity'."""
        self._login()
        self._inject(Decimal("1000.00"))

        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)
        related_titles = [v["title"] for v in response.context["related_views"]]
        self.assertIn("Balance Project", related_titles)
        self.assertNotIn("Entity", related_titles)

    def test_only_payment_transactions_are_listed(self):
        """Issuance transactions (no cash flow) must be excluded."""
        self._login()
        # _inject_funds creates both a CORRECTION_CREDIT_ISSUANCE and a
        # CORRECTION_CREDIT_PAYMENT; only the payment type must be listed.
        self._inject(Decimal("1000.00"))

        response = self.client.get(self._url())
        transactions = response.context["transactions"]

        self.assertEqual(len(transactions), 1)
        self.assertEqual(
            transactions[0].type, TransactionType.CORRECTION_CREDIT_PAYMENT
        )

    def test_incoming_and_outgoing_are_shown_with_directions(self):
        """Both incoming and outgoing payment transactions are listed."""
        self._login()
        self._inject(Decimal("1000.00"))  # incoming (target)
        self._outgoing(Decimal("200.00"))  # outgoing (source)

        response = self.client.get(self._url())
        transactions = response.context["transactions"]

        self.assertEqual(len(transactions), 2)
        self.assertEqual(
            {tx.direction for tx in transactions}, {"incoming", "outgoing"}
        )

    def test_running_balance_and_totals_are_computed(self):
        """Running balance, totals and current balance are correct."""
        self._login()
        self._inject(Decimal("1000.00"))
        self._outgoing(Decimal("200.00"))

        response = self.client.get(self._url())
        transactions = response.context["transactions"]

        # Ordered by date, then pk: the injection payment comes first.
        self.assertEqual(transactions[0].direction, "incoming")
        self.assertEqual(transactions[0].running_balance, Decimal("1000.00"))
        self.assertEqual(transactions[1].direction, "outgoing")
        self.assertEqual(transactions[1].running_balance, Decimal("800.00"))

        self.assertEqual(response.context["total_incoming"], Decimal("1000.00"))
        self.assertEqual(response.context["total_outgoing"], Decimal("200.00"))
        self.assertEqual(response.context["current_balance"], Decimal("800.00"))

    def test_transactions_for_other_entities_are_excluded(self):
        """Only transactions where the entity is source or target are listed."""
        self._login()
        self._inject(Decimal("1000.00"))
        other = _make_entity("Other Project", EntityType.PROJECT)

        url = reverse(
            "entity_payment_transactions_list", kwargs={"entity_pk": other.pk}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["transactions"]), 0)

    def test_nonexistent_entity_returns_404(self):
        """Requesting a non-existent entity returns 404."""
        self._login()
        url = reverse("entity_payment_transactions_list", kwargs={"entity_pk": 99999})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_user_redirected(self):
        """Unauthenticated users are redirected away from the page."""
        self._inject(Decimal("1000.00"))
        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 302)

    def test_pagination_splits_transactions(self):
        """The list is paginated (25 per page) with a working page 2."""
        self._login()
        self._inject(Decimal("1000.00"))  # 1 incoming transaction

        vendor = _make_entity("Vendor Pagination", EntityType.PERSON, is_vendor=True)
        _make_vendor_stakeholder(self.entity, vendor)
        for i in range(26):
            op = PurchaseOperation.objects.create(
                source=self.entity,
                destination=vendor,
                amount=Decimal("10.00"),
                operation_type=OperationType.PURCHASE,
                date=timezone.now().date(),
                officer=self.officer,
                description=f"Bulk purchase {i}",
            )
            op.create_payment_transaction(
                amount=Decimal("10.00"),
                officer=self.officer,
                date=timezone.now().date(),
            )

        # 1 incoming + 26 outgoing = 27 payment transactions -> 2 pages.
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["transactions"]), 25)
        self.assertTrue(response.context["page_obj"].has_next)

        response2 = self.client.get(f"{self._url()}?page=2")
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response2.context["page_obj"].number, 2)
        self.assertEqual(len(response2.context["transactions"]), 2)


class TransactionDetailViewTests(TestCase):
    """Test the transaction detail view (entry point for reversal)."""

    def setUp(self):
        self.client = Client()
        self.officer = _make_officer()
        self.system = _get_or_create_system()
        self.entity = _make_entity("Detail Project", EntityType.PROJECT)

    def _create_transaction(self):
        """Create an incoming CORRECTION_CREDIT_PAYMENT transaction."""
        _inject_funds(self.entity, Decimal("1000.00"), self.officer)
        return Transaction.objects.filter(
            type=TransactionType.CORRECTION_CREDIT_PAYMENT
        ).first()

    def _url(self, tx):
        return reverse("transaction_detail", kwargs={"transaction_pk": tx.pk})

    def test_authorized_user_can_load_transaction_detail(self):
        """Logged-in user can view the transaction detail page."""
        self.client.force_login(self.officer)
        tx = self._create_transaction()
        self.assertIsNotNone(tx)

        response = self.client.get(self._url(tx))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["transaction"], tx)
        self.assertTrue(response.context["can_reverse"])

    def test_unauthenticated_user_redirected(self):
        """Unauthenticated users are redirected away from the page."""
        tx = self._create_transaction()
        self.assertIsNotNone(tx)

        response = self.client.get(self._url(tx))

        self.assertEqual(response.status_code, 302)

    def test_nonexistent_transaction_returns_404(self):
        """Requesting a non-existent transaction returns 404."""
        self.client.force_login(self.officer)
        url = reverse("transaction_detail", kwargs={"transaction_pk": 99999})

        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_active_transaction_can_be_reversed(self):
        """An active (non-reversed, non-reversal) transaction can be reversed."""
        self.client.force_login(self.officer)
        tx = self._create_transaction()
        self.assertIsNotNone(tx)

        response = self.client.get(self._url(tx))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["can_reverse"])
        self.assertContains(
            response,
            reverse("transaction_reverse_view", kwargs={"pk": tx.pk}),
        )

    def test_reversed_transaction_cannot_be_reversed(self):
        """A reversed transaction is not offered for reversal."""
        self.client.force_login(self.officer)
        tx = self._create_transaction()
        self.assertIsNotNone(tx)
        tx.reverse(officer=self.officer, reason="Test reversal")

        response = self.client.get(self._url(tx))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_reverse"])

    def test_reversal_transaction_cannot_be_reversed(self):
        """A reversal transaction is not offered for reversal."""
        self.client.force_login(self.officer)
        tx = self._create_transaction()
        self.assertIsNotNone(tx)
        reversal = tx.reverse(officer=self.officer, reason="Test reversal")

        response = self.client.get(
            reverse("transaction_detail", kwargs={"transaction_pk": reversal.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_reverse"])


# =============================================================================
# Entity Payables List View Tests
# =============================================================================


class EntityPayablesViewTests(TestCase):
    """Test the entity payables list view used to track outstanding payables."""

    def setUp(self):
        self.client = Client()
        self.officer = _make_officer()
        self.entity = _make_entity("Payables Project", EntityType.PROJECT)
        self.vendor = _make_entity("Payables Vendor", EntityType.PERSON, is_vendor=True)
        _make_vendor_stakeholder(self.entity, self.vendor)

    def _url(self):
        return reverse("entity_payables_list", kwargs={"entity_pk": self.entity.pk})

    def _login(self):
        self.client.force_login(self.officer)

    def _make_purchase_issuance(self, amount=Decimal("500.00")):
        """Create a PURCHASE operation (generates PURCHASE_ISSUANCE -> payables)."""
        return PurchaseOperation.objects.create(
            source=self.entity,
            destination=self.vendor,
            amount=amount,
            operation_type=OperationType.PURCHASE,
            date=timezone.now().date(),
            officer=self.officer,
            description="Test purchase",
        )

    def _pay(self, op, amount=Decimal("200.00")):
        """Pay part of a purchase (generates PURCHASE_PAYMENT -> reduces payables)."""
        op.create_payment_transaction(
            amount=amount,
            officer=self.officer,
            date=timezone.now().date(),
        )

    def test_authorized_user_can_load_entity_payables(self):
        """Logged-in user can view the entity payables page."""
        self._login()
        self._make_purchase_issuance(Decimal("500.00"))

        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["entity"], self.entity)
        self.assertEqual(len(response.context["transactions"]), 1)

    def test_payables_show_issuance_and_payment(self):
        """Issuance increases payables, payment decreases them."""
        self._login()
        # Inject funds so the purchase payment can be recorded (the injected
        # CAPITAL_GAIN transactions are not payables types and stay excluded).
        _inject_funds(self.entity, Decimal("1000.00"), self.officer)
        op = self._make_purchase_issuance(Decimal("500.00"))
        self._pay(op, Decimal("200.00"))

        response = self.client.get(self._url())
        transactions = response.context["transactions"]

        self.assertEqual(len(transactions), 2)
        self.assertEqual(transactions[0].type, TransactionType.PURCHASE_ISSUANCE)
        self.assertEqual(transactions[0].direction, "increase")
        self.assertEqual(transactions[0].running_balance, Decimal("500.00"))
        self.assertEqual(transactions[1].type, TransactionType.PURCHASE_PAYMENT)
        self.assertEqual(transactions[1].direction, "decrease")
        self.assertEqual(transactions[1].running_balance, Decimal("300.00"))

        self.assertEqual(response.context["total_increase"], Decimal("500.00"))
        self.assertEqual(response.context["total_decrease"], Decimal("200.00"))
        self.assertEqual(response.context["current_obligation"], Decimal("300.00"))

    def test_non_payable_transactions_are_excluded(self):
        """CORRECTION_CREDIT_PAYMENT (not a payable) must be excluded."""
        self._login()
        _inject_funds(self.entity, Decimal("1000.00"), self.officer)

        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["transactions"]), 0)

    def test_nonexistent_entity_returns_404(self):
        """Requesting a non-existent entity returns 404."""
        self._login()
        url = reverse("entity_payables_list", kwargs={"entity_pk": 99999})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_user_redirected(self):
        """Unauthenticated users are redirected away from the page."""
        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 302)

    def test_pagination_splits_payables(self):
        """The payables list is paginated (25 per page) with a working page 2."""
        self._login()
        for i in range(26):
            self._make_purchase_issuance(Decimal("10.00"))

        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["transactions"]), 25)
        self.assertTrue(response.context["page_obj"].has_next)

        response2 = self.client.get(f"{self._url()}?page=2")
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response2.context["page_obj"].number, 2)
        self.assertEqual(len(response2.context["transactions"]), 1)


class EntityReceivablesViewTests(TestCase):
    """Test the entity receivables list view used to track outstanding receivables."""

    def setUp(self):
        self.client = Client()
        self.officer = _make_officer()
        self.system = _get_or_create_system()
        self.entity = _make_entity("Receivables Project", EntityType.PROJECT)
        self.worker = _make_entity("Ali Worker", EntityType.PERSON, is_worker=True)
        Stakeholder(
            parent=self.entity,
            target=self.worker,
            role=StakeholderRole.WORKER,
            active=True,
        ).save()

    def _url(self):
        return reverse("entity_receivables_list", kwargs={"entity_pk": self.entity.pk})

    def _login(self):
        self.client.force_login(self.officer)

    def _make_worker_advance(self, amount=Decimal("500.00")):
        """Create a WorkerAdvance (generates WORKER_ADVANCE_PAYMENT -> receivables)."""
        _inject_funds(self.entity, Decimal("1000.00"), self.officer)
        return WorkerAdvanceOperation.objects.create(
            source=self.entity,
            destination=self.worker,
            amount=amount,
            operation_type=OperationType.WORKER_ADVANCE,
            date=timezone.now().date(),
            officer=self.officer,
            description="Test worker advance",
        )

    def test_authorized_user_can_load_entity_receivables(self):
        """Logged-in user can view the entity receivables page."""
        self._login()
        self._make_worker_advance(Decimal("500.00"))

        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["entity"], self.entity)
        self.assertEqual(len(response.context["transactions"]), 1)

    def test_receivables_show_advance_and_repayment(self):
        """Advance increases receivables, repayment decreases them."""
        self._login()
        op = self._make_worker_advance(Decimal("500.00"))
        op.create_repayment_transaction(
            amount=Decimal("200.00"),
            officer=self.officer,
            date=timezone.now().date(),
        )

        response = self.client.get(self._url())
        transactions = response.context["transactions"]

        self.assertEqual(len(transactions), 2)
        self.assertEqual(transactions[0].type, TransactionType.WORKER_ADVANCE_PAYMENT)
        self.assertEqual(transactions[0].direction, "increase")
        self.assertEqual(transactions[0].running_balance, Decimal("500.00"))
        self.assertEqual(transactions[1].type, TransactionType.WORKER_ADVANCE_REPAYMENT)
        self.assertEqual(transactions[1].direction, "decrease")
        self.assertEqual(transactions[1].running_balance, Decimal("300.00"))

        self.assertEqual(response.context["total_increase"], Decimal("500.00"))
        self.assertEqual(response.context["total_decrease"], Decimal("200.00"))
        self.assertEqual(response.context["current_obligation"], Decimal("300.00"))

    def test_non_receivable_transactions_are_excluded(self):
        """CAPITAL_GAIN_PAYMENT (not a receivable) must be excluded."""
        self._login()
        _inject_funds(self.entity, Decimal("1000.00"), self.officer)

        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["transactions"]), 0)

    def test_nonexistent_entity_returns_404(self):
        """Requesting a non-existent entity returns 404."""
        self._login()
        url = reverse("entity_receivables_list", kwargs={"entity_pk": 99999})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_user_redirected(self):
        """Unauthenticated users are redirected away from the page."""
        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 302)

    def test_pagination_splits_receivables(self):
        """The receivables list is paginated (25 per page) with a working page 2."""
        self._login()
        for i in range(26):
            self._make_worker_advance(Decimal("10.00"))

        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["transactions"]), 25)
        self.assertTrue(response.context["page_obj"].has_next)

        response2 = self.client.get(f"{self._url()}?page=2")
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response2.context["page_obj"].number, 2)
        self.assertEqual(len(response2.context["transactions"]), 1)


class EntityObligationRepaymentReversalTests(TestCase):
    """
    Regression tests: reversing a worker-advance repayment must not leak a
    phantom row into the project's payables, and must keep the project's
    receivable (and the worker's payable) intact.
    """

    def setUp(self):
        self.client = Client()
        self.officer = _make_officer()
        self.system = _get_or_create_system()
        self.project = _make_entity("Oblig Project", EntityType.PROJECT)
        self.worker = _make_entity("Oblig Worker", EntityType.PERSON, is_worker=True)
        Stakeholder(
            parent=self.project,
            target=self.worker,
            role=StakeholderRole.WORKER,
            active=True,
        ).save()
        _inject_funds(self.project, Decimal("5000.00"), self.officer)

    def _advance_repay_full_and_reverse(self):
        """Advance 1000 to the worker, repay it in full, then reverse the repayment."""
        op = WorkerAdvanceOperation.objects.create(
            source=self.project,
            destination=self.worker,
            amount=Decimal("1000.00"),
            operation_type=OperationType.WORKER_ADVANCE,
            date=timezone.now().date(),
            officer=self.officer,
            description="Test worker advance",
        )
        op.create_repayment_transaction(
            amount=Decimal("1000.00"),
            officer=self.officer,
            date=timezone.now().date(),
        )
        repayment = op.get_all_transactions().get(
            type=TransactionType.WORKER_ADVANCE_REPAYMENT,
            reversal_of__isnull=True,
        )
        repayment.reverse(officer=self.officer)
        return op

    def test_reversed_repayment_does_not_create_phantom_payables(self):
        """Project payables must stay 0 and the receivable must stay 1000."""
        self._advance_repay_full_and_reverse()

        self.project.refresh_from_db()
        self.assertEqual(self.project.payables, Decimal("0.00"))
        self.assertEqual(self.project.receivables, Decimal("1000.00"))

    def test_worker_still_owes_advance_after_repayment_reversed(self):
        """The worker's payable returns to the full advance after the reversal."""
        self._advance_repay_full_and_reverse()

        self.worker.refresh_from_db()
        self.assertEqual(self.worker.payables, Decimal("1000.00"))
        self.assertEqual(self.worker.receivables, Decimal("0.00"))

    def test_payables_page_excludes_repayment_reversal_mirror(self):
        """The project's payables page must not list the reversal mirror row."""
        self._advance_repay_full_and_reverse()
        self.client.force_login(self.officer)
        url = reverse("entity_payables_list", kwargs={"entity_pk": self.project.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["transactions"]), 0)
        self.assertEqual(response.context["total_increase"], Decimal("0.00"))
        self.assertEqual(response.context["total_decrease"], Decimal("0.00"))
        self.assertEqual(response.context["current_obligation"], Decimal("0.00"))

    def test_receivables_page_still_shows_advance_after_repayment_reversed(self):
        """The project's receivables page keeps the advance as the only row."""
        self._advance_repay_full_and_reverse()
        self.client.force_login(self.officer)
        url = reverse("entity_receivables_list", kwargs={"entity_pk": self.project.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        transactions = response.context["transactions"]
        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].type, TransactionType.WORKER_ADVANCE_PAYMENT)
        self.assertEqual(transactions[0].direction, "increase")
        self.assertEqual(response.context["total_increase"], Decimal("1000.00"))
        self.assertEqual(response.context["total_decrease"], Decimal("0.00"))
        self.assertEqual(response.context["current_obligation"], Decimal("1000.00"))
