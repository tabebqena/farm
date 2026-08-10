from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import ProductLedgerEntry, ProductTemplate
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CapitalGainOperation, PurchaseOperation
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
    return Entity.create(EntityType.PERSON, name=name)
    return person.entity


def _make_project_entity(name):
    return Entity.create(EntityType.PROJECT, name=name)


def _make_vendor_entity(name):
    return Entity.create(EntityType.PERSON, name=name, is_vendor=True)


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


def _make_vendor_stakeholder(project_entity, vendor_entity, active=True):
    sh = Stakeholder(
        parent=project_entity,
        target=vendor_entity,
        role=StakeholderRole.VENDOR,
        active=active,
    )
    sh.save()
    return sh


# ---------------------------------------------------------------------------
# PurchaseCreateTest
# ---------------------------------------------------------------------------


class PurchaseCreateTest(TestCase):
    """
    Tests for purchase operation creation: validation, issuance transaction, and
    fund behaviour.

    On save, only a PURCHASE_ISSUANCE transaction is created (obligation record).
    PURCHASE_ISSUANCE is a non-cash transaction — it does NOT affect fund balances.
    Cash movement only happens later via create_payment_transaction().
    """

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.officer_user = _make_officer()

        self.project_entity = _make_project_entity("Test Farm Project")
        _inject_project(
            self.system_entity,
            self.project_entity,
            Decimal("5000.00"),
            self.officer_user,
        )

        self.vendor_entity = _make_vendor_entity("Agri Supplies Ltd")
        _make_vendor_stakeholder(self.project_entity, self.vendor_entity)

    def _make_op(self, **kwargs):
        defaults = dict(
            source=self.project_entity,
            destination=self.vendor_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.PURCHASE,
            date=date.today(),
            description="Test purchase",
            officer=self.officer_user,
        )
        defaults.update(kwargs)
        return PurchaseOperation(**defaults)

    # ------------------------------------------------------------------
    # Happy path — issuance only on creation
    # ------------------------------------------------------------------

    def test_save_creates_exactly_one_issuance_transaction(self):
        op = self._make_op()
        op.save()

        transactions = op.get_all_transactions()
        self.assertEqual(transactions.count(), 1)
        self.assertTrue(
            transactions.filter(type=TransactionType.PURCHASE_ISSUANCE).exists(),
            "Issuance transaction must be created on save",
        )

    def test_no_payment_transaction_created_on_save(self):
        op = self._make_op()
        op.save()

        self.assertFalse(
            op.get_all_transactions()
            .filter(type=TransactionType.PURCHASE_PAYMENT)
            .exists(),
            "Payment transaction must NOT be created on save — purchase is not one-shot",
        )

    def test_issuance_transaction_direction_is_project_to_vendor(self):
        op = self._make_op()
        op.save()

        tx = op.get_all_transactions().get(type=TransactionType.PURCHASE_ISSUANCE)
        self.assertEqual(tx.source, self.project_entity)
        self.assertEqual(tx.target, self.vendor_entity)

    def test_issuance_transaction_amount_matches_operation(self):
        op = self._make_op(amount=Decimal("750.00"))
        op.save()

        tx = op.get_all_transactions().get(type=TransactionType.PURCHASE_ISSUANCE)
        self.assertEqual(tx.amount, Decimal("750.00"))

    def test_project_fund_balance_unchanged_after_save(self):
        """PURCHASE_ISSUANCE is non-cash; it does not affect fund balances."""
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

    def test_destination_must_be_a_vendor_entity(self):
        non_vendor = _make_person_entity("Not A Vendor")
        op = self._make_op(destination=non_vendor)
        with self.assertRaises(ValidationError):
            op.save()

    # BUG the vendor can be a project
    def test_destination_project_entity_raises_validation_error(self):
        other_project = _make_project_entity("Some Project")
        op = self._make_op(destination=other_project)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_must_be_active_stakeholder_vendor(self):
        unregistered_vendor = _make_vendor_entity("Unregistered Vendor")
        # is_vendor=True but no Stakeholder relationship with this project
        op = self._make_op(destination=unregistered_vendor)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_with_inactive_stakeholder_raises_validation_error(self):
        inactive_vendor = _make_vendor_entity("Inactive Vendor")
        _make_vendor_stakeholder(self.project_entity, inactive_vendor, active=False)

        op = self._make_op(destination=inactive_vendor)
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


# ---------------------------------------------------------------------------
# Helpers for create_from_session tests
# ---------------------------------------------------------------------------


def _make_product_template(name, project):
    """Create a ProductTemplate and link it to a project."""
    pt = ProductTemplate.objects.create(
        name=name,
        nature=ProductTemplate.Nature.ANIMAL,
        sub_category="Cattle",
        tracking_mode=ProductTemplate.TrackingMode.BATCH,
        default_unit="Head",
    )
    pt.entities.add(project)
    return pt


def _session_data(
    *,
    vendor_id,
    total_amount,
    items,
    date_str=None,
    description="Test purchase from session",
    amount_paid="0",
):
    """Build a minimal session data dict matching the wizard format."""
    return {
        "date": date_str or date.today().isoformat(),
        "vendor_id": vendor_id,
        "description": description,
        "total_amount": str(total_amount),
        "amount_paid": str(amount_paid),
        "items": items,
    }


def _item_data(
    product_template_id,
    quantity="10.00",
    unit_price="100.00",
    received_qty="0",
    description="",
    unique_id="",
):
    """Build a single item dict as stored in the wizard session."""
    return {
        "product_template_id": product_template_id,
        "quantity": quantity,
        "unit_price": unit_price,
        "received_qty": received_qty,
        "description": description,
        "unique_id": unique_id,
    }


# ---------------------------------------------------------------------------
# PurchaseCreateFromSessionTest
# ---------------------------------------------------------------------------


class PurchaseCreateFromSessionTest(TestCase):
    """
    Tests for PurchaseOperation.create_from_session() — the factory method
    used by the purchase wizard to persist all data inside a single atomic
    transaction.

    This method orchestrates:
      1. Integrity check (item totals vs declared total)
      2. PurchaseOperation record + issuance transaction
      3. InvoiceItem records
      4. InventoryMovementLine for any received quantities
      5. ProductLedgerEntry for issuance
      6. Payment transaction (if amount_paid > 0)
    """

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.officer_user = User.objects.create_user(
            username="session_officer", password="testpass", is_staff=True
        )

        self.project_entity = Entity.create(EntityType.PROJECT, name="Session Farm")
        _inject_project(
            self.system_entity,
            self.project_entity,
            Decimal("10000.00"),
            self.officer_user,
        )

        self.vendor_entity = Entity.create(
            EntityType.PERSON, name="Session Vendor", is_vendor=True
        )
        _make_vendor_stakeholder(self.project_entity, self.vendor_entity)

        self.template = _make_product_template("Test Animal", self.project_entity)

    # ------------------------------------------------------------------
    # Happy path — basic creation without inventory movement or payment
    # ------------------------------------------------------------------

    def test_create_from_session_basic(self):
        """Basic creation: operation, issuance, invoice items, ledger entries."""
        items = [_item_data(self.template.pk)]
        session = _session_data(
            vendor_id=self.vendor_entity.pk,
            total_amount=Decimal("1000.00"),
            items=items,
        )

        op = PurchaseOperation.create_from_session(
            project=self.project_entity,
            session_data=session,
            officer=self.officer_user,
        )

        # Operation is persisted with correct attributes
        self.assertIsNotNone(op.pk)
        self.assertEqual(op.source, self.project_entity)
        self.assertEqual(op.destination, self.vendor_entity)
        self.assertEqual(op.amount, Decimal("1000.00"))
        self.assertEqual(op.operation_type, OperationType.PURCHASE)

        # Exactly one issuance transaction (no payment)
        transactions = op.get_all_transactions()
        self.assertEqual(transactions.count(), 1)
        self.assertTrue(
            transactions.filter(type=TransactionType.PURCHASE_ISSUANCE).exists()
        )

        # Invoice items created
        self.assertEqual(op.items.count(), 1)
        invoice_item = op.items.first()
        self.assertEqual(invoice_item.product_template, self.template)
        self.assertEqual(invoice_item.quantity, Decimal("10.00"))
        self.assertEqual(invoice_item.unit_price, Decimal("100.00"))

        # No inventory movement lines (received_qty = 0)
        self.assertEqual(op.movement_lines.count(), 0)

        # Product ledger entries recorded
        self.assertTrue(ProductLedgerEntry.objects.filter(operation=op).exists())

    def test_create_from_session_multiple_items(self):
        """Multiple invoice items are created and totals validated."""
        items = [
            _item_data(self.template.pk, quantity="5.00", unit_price="100.00"),
            _item_data(self.template.pk, quantity="3.00", unit_price="50.00"),
        ]
        session = _session_data(
            vendor_id=self.vendor_entity.pk,
            total_amount=Decimal("650.00"),  # 5*100 + 3*50 = 650
            items=items,
        )

        op = PurchaseOperation.create_from_session(
            project=self.project_entity,
            session_data=session,
            officer=self.officer_user,
        )

        self.assertEqual(op.items.count(), 2)
        self.assertEqual(op.amount, Decimal("650.00"))

    def test_create_from_session_creates_issuance_transaction(self):
        """Verify the issuance transaction details."""
        items = [_item_data(self.template.pk)]
        session = _session_data(
            vendor_id=self.vendor_entity.pk,
            total_amount=Decimal("500.00"),
            items=items,
        )

        op = PurchaseOperation.create_from_session(
            project=self.project_entity,
            session_data=session,
            officer=self.officer_user,
        )

        tx = op.get_all_transactions().get(type=TransactionType.PURCHASE_ISSUANCE)
        self.assertEqual(tx.source, self.project_entity)
        self.assertEqual(tx.target, self.vendor_entity)
        self.assertEqual(tx.amount, Decimal("500.00"))

    # ------------------------------------------------------------------
    # Happy path — with inventory movement (received quantities)
    # ------------------------------------------------------------------

    def test_create_from_session_with_received_qty(self):
        """InventoryMovementLine records are created when received_qty > 0."""
        items = [
            _item_data(
                self.template.pk,
                quantity="10.00",
                unit_price="100.00",
                received_qty="10.00",
            )
        ]
        session = _session_data(
            vendor_id=self.vendor_entity.pk,
            total_amount=Decimal("1000.00"),
            items=items,
        )

        op = PurchaseOperation.create_from_session(
            project=self.project_entity,
            session_data=session,
            officer=self.officer_user,
        )

        # Movement line created
        self.assertEqual(op.movement_lines.count(), 1)
        ml = op.movement_lines.first()
        self.assertEqual(ml.quantity, Decimal("10.00"))
        self.assertEqual(ml.officer, self.officer_user)

        # Product was lazy-created by the movement line save
        self.assertIsNotNone(ml.product)
        self.assertEqual(ml.product.product_template, self.template)

        # Invoice item linked to the movement line
        invoice_item = op.items.first()
        self.assertEqual(ml.invoice_item, invoice_item)

    def test_create_from_session_partial_received_qty(self):
        """Partial receipt creates a movement line only for the received quantity."""
        items = [
            _item_data(
                self.template.pk,
                quantity="10.00",
                unit_price="100.00",
                received_qty="4.00",
            )
        ]
        session = _session_data(
            vendor_id=self.vendor_entity.pk,
            total_amount=Decimal("1000.00"),
            items=items,
        )

        op = PurchaseOperation.create_from_session(
            project=self.project_entity,
            session_data=session,
            officer=self.officer_user,
        )

        self.assertEqual(op.movement_lines.count(), 1)
        self.assertEqual(op.movement_lines.first().quantity, Decimal("4.00"))

    # ------------------------------------------------------------------
    # Happy path — with initial payment
    # ------------------------------------------------------------------

    def test_create_from_session_with_payment(self):
        """Payment transaction is created when amount_paid > 0."""
        items = [_item_data(self.template.pk)]
        session = _session_data(
            vendor_id=self.vendor_entity.pk,
            total_amount=Decimal("1000.00"),
            items=items,
            amount_paid="400.00",
        )

        op = PurchaseOperation.create_from_session(
            project=self.project_entity,
            session_data=session,
            officer=self.officer_user,
        )

        transactions = op.get_all_transactions()
        # 1 issuance + 1 payment = 2
        self.assertEqual(transactions.count(), 2)
        self.assertTrue(
            transactions.filter(type=TransactionType.PURCHASE_PAYMENT).exists()
        )

        # Fund balances reflect the payment
        self.project_entity.refresh_from_db()
        self.assertEqual(
            self.project_entity.balance,
            Decimal("10000.00") - Decimal("400.00"),
        )

        self.vendor_entity.refresh_from_db()
        self.assertEqual(
            self.vendor_entity.balance,
            Decimal("400.00"),
        )

        # Settlement state updated
        self.assertEqual(op.amount_remaining_to_settle, Decimal("600.00"))
        self.assertFalse(op.is_fully_settled)

    def test_create_from_session_zero_payment(self):
        """Zero amount_paid does not create a payment transaction."""
        items = [_item_data(self.template.pk)]
        session = _session_data(
            vendor_id=self.vendor_entity.pk,
            total_amount=Decimal("1000.00"),
            items=items,
            amount_paid="0",
        )

        op = PurchaseOperation.create_from_session(
            project=self.project_entity,
            session_data=session,
            officer=self.officer_user,
        )

        transactions = op.get_all_transactions()
        self.assertEqual(transactions.count(), 1)
        self.assertFalse(
            transactions.filter(type=TransactionType.PURCHASE_PAYMENT).exists()
        )

    def test_create_from_session_full_payment(self):
        """Full amount_paid marks operation as fully settled."""
        items = [_item_data(self.template.pk)]
        session = _session_data(
            vendor_id=self.vendor_entity.pk,
            total_amount=Decimal("1000.00"),
            items=items,
            amount_paid="1000.00",
        )

        op = PurchaseOperation.create_from_session(
            project=self.project_entity,
            session_data=session,
            officer=self.officer_user,
        )

        self.assertTrue(op.is_fully_settled)
        self.assertEqual(op.amount_remaining_to_settle, Decimal("0.00"))

    # ------------------------------------------------------------------
    # Happy path — combined: received quantity + payment
    # ------------------------------------------------------------------

    def test_create_from_session_full_flow(self):
        """Full flow: items, received quantities, and initial payment."""
        items = [
            _item_data(
                self.template.pk,
                quantity="20.00",
                unit_price="50.00",
                received_qty="15.00",
            )
        ]
        session = _session_data(
            vendor_id=self.vendor_entity.pk,
            total_amount=Decimal("1000.00"),
            items=items,
            amount_paid="300.00",
        )

        op = PurchaseOperation.create_from_session(
            project=self.project_entity,
            session_data=session,
            officer=self.officer_user,
        )

        # Operation created
        self.assertIsNotNone(op.pk)
        self.assertEqual(op.amount, Decimal("1000.00"))

        # Invoice items
        self.assertEqual(op.items.count(), 1)

        # Movement lines
        self.assertEqual(op.movement_lines.count(), 1)
        self.assertEqual(op.movement_lines.first().quantity, Decimal("15.00"))

        # Transactions: 1 issuance + 1 payment = 2
        self.assertEqual(op.get_all_transactions().count(), 2)

        # Ledger entries
        self.assertTrue(ProductLedgerEntry.objects.filter(operation=op).exists())

        # Fund balances
        self.project_entity.refresh_from_db()
        self.assertEqual(
            self.project_entity.balance,
            Decimal("10000.00") - Decimal("300.00"),
        )

    # ------------------------------------------------------------------
    # Validation — item totals mismatch
    # ------------------------------------------------------------------

    def test_create_from_session_item_totals_mismatch(self):
        """ValueError when item totals do not match declared total."""
        items = [
            _item_data(self.template.pk, quantity="5.00", unit_price="100.00"),
            # 5*100 = 500, but declaring 600
        ]
        session = _session_data(
            vendor_id=self.vendor_entity.pk,
            total_amount=Decimal("600.00"),
            items=items,
        )

        with self.assertRaises(ValueError):
            PurchaseOperation.create_from_session(
                project=self.project_entity,
                session_data=session,
                officer=self.officer_user,
            )

    def test_create_from_session_item_totals_slight_mismatch(self):
        """Mismatch greater than 0.01 tolerance raises ValueError."""
        items = [
            _item_data(self.template.pk, quantity="5.00", unit_price="100.00"),
        ]
        # 5*100 = 500, declaring 500.02 -> difference of 0.02 > 0.01 tolerance
        session = _session_data(
            vendor_id=self.vendor_entity.pk,
            total_amount=Decimal("500.02"),
            items=items,
        )

        with self.assertRaises(ValueError):
            PurchaseOperation.create_from_session(
                project=self.project_entity,
                session_data=session,
                officer=self.officer_user,
            )

    def test_create_from_session_item_totals_within_tolerance(self):
        """Mismatch within 0.01 tolerance is accepted."""
        items = [
            _item_data(self.template.pk, quantity="5.00", unit_price="100.00"),
        ]
        # 5*100 = 500, declaring 500.01 -> difference of 0.01, within tolerance
        session = _session_data(
            vendor_id=self.vendor_entity.pk,
            total_amount=Decimal("500.01"),
            items=items,
        )

        op = PurchaseOperation.create_from_session(
            project=self.project_entity,
            session_data=session,
            officer=self.officer_user,
        )

        self.assertIsNotNone(op.pk)

    # ------------------------------------------------------------------
    # Validation — missing / invalid vendor
    # ------------------------------------------------------------------

    def test_create_from_session_missing_vendor_raises_error(self):
        """ValidationError when vendor has been deleted."""
        deleted_pk = self.vendor_entity.pk + 9999  # non-existent PK
        items = [_item_data(self.template.pk)]
        session = _session_data(
            vendor_id=deleted_pk,
            total_amount=Decimal("1000.00"),
            items=items,
        )

        with self.assertRaises(ValidationError):
            PurchaseOperation.create_from_session(
                project=self.project_entity,
                session_data=session,
                officer=self.officer_user,
            )

    # ------------------------------------------------------------------
    # Validation — payment exceeds total
    # ------------------------------------------------------------------

    def test_create_from_session_payment_exceeds_total(self):
        """ValueError when amount_paid exceeds declared total."""
        items = [_item_data(self.template.pk)]
        session = _session_data(
            vendor_id=self.vendor_entity.pk,
            total_amount=Decimal("1000.00"),
            items=items,
            amount_paid="1500.00",
        )

        with self.assertRaises(ValueError):
            PurchaseOperation.create_from_session(
                project=self.project_entity,
                session_data=session,
                officer=self.officer_user,
            )

    # ------------------------------------------------------------------
    # Validation — missing session data
    # ------------------------------------------------------------------

    def test_create_from_session_missing_items_raises_error(self):
        """KeyError when items key is missing from session data."""
        session = _session_data(
            vendor_id=self.vendor_entity.pk,
            total_amount=Decimal("1000.00"),
            items=[_item_data(self.template.pk)],
        )
        del session["items"]  # remove items key

        with self.assertRaises(KeyError):
            PurchaseOperation.create_from_session(
                project=self.project_entity,
                session_data=session,
                officer=self.officer_user,
            )

    def test_create_from_session_empty_items_raises_error(self):
        """Empty items list raises ValueError from totals validation."""
        session = _session_data(
            vendor_id=self.vendor_entity.pk,
            total_amount=Decimal("0.00"),
            items=[],
        )

        with self.assertRaises(ValueError):
            PurchaseOperation.create_from_session(
                project=self.project_entity,
                session_data=session,
                officer=self.officer_user,
            )

    # ------------------------------------------------------------------
    # ProductLedgerEntry verification
    # ------------------------------------------------------------------

    def test_create_from_session_ledger_entries_created(self):
        """ProductLedgerEntry records are created for issuance."""
        items = [_item_data(self.template.pk)]
        session = _session_data(
            vendor_id=self.vendor_entity.pk,
            total_amount=Decimal("1000.00"),
            items=items,
        )

        op = PurchaseOperation.create_from_session(
            project=self.project_entity,
            session_data=session,
            officer=self.officer_user,
        )

        entries = ProductLedgerEntry.objects.filter(operation=op)
        self.assertTrue(entries.exists())

        # Verify entry references the invoice item
        invoice_item = op.items.first()
        self.assertTrue(entries.filter(invoice_item=invoice_item).exists())

    # ------------------------------------------------------------------
    # Edge cases — description handling
    # ------------------------------------------------------------------

    def test_create_from_session_empty_description(self):
        """Empty description in session results in blank description on operation."""
        items = [_item_data(self.template.pk)]
        session = _session_data(
            vendor_id=self.vendor_entity.pk,
            total_amount=Decimal("1000.00"),
            items=items,
            description="",
        )

        op = PurchaseOperation.create_from_session(
            project=self.project_entity,
            session_data=session,
            officer=self.officer_user,
        )

        self.assertEqual(op.description, "")

    def test_create_from_session_custom_date(self):
        """Operation date matches the date provided in session data."""
        custom_date = "2024-06-15"
        items = [_item_data(self.template.pk)]
        session = _session_data(
            vendor_id=self.vendor_entity.pk,
            total_amount=Decimal("1000.00"),
            items=items,
            date_str=custom_date,
        )

        op = PurchaseOperation.create_from_session(
            project=self.project_entity,
            session_data=session,
            officer=self.officer_user,
        )

        self.assertEqual(op.date.isoformat(), custom_date)

    def test_destination_is_immutable_after_save(self):
        op = self._make_op()
        op.save()

        other_vendor = _make_vendor_entity("Other Vendor")
        _make_vendor_stakeholder(self.project_entity, other_vendor)
        op.destination = other_vendor
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_is_immutable_after_save(self):
        op = self._make_op()
        op.save()

        op.amount = Decimal("9999.00")
        with self.assertRaises(ValidationError):
            op.save()
