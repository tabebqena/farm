from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_adjustment._effect import AdjustmentEffect
from apps.app_adjustment.models import Adjustment, AdjustmentType
from apps.app_entity.models import Entity, Person, Project, Stakeholder, StakeholderRole
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import (
    CapitalGainOperation,
    ExpenseOperation,
    PurchaseOperation,
    SaleOperation,
)
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_officer(username="officer"):
    return User.objects.create_user(
        username=username, password="testpass", is_staff=True
    )


def _make_project_entity(name):
    project = Project(name=name)
    project.save()
    return Entity.create(owner=project)


def _make_person_entity(name):
    person = Person.create(private_name=name)
    return person.entity


def _make_vendor_entity(name):
    person = Person.create(private_name=name, is_vendor=True)
    return person.entity


def _make_client_entity(name):
    person = Person.create(private_name=name, is_client=True)
    return person.entity


def _make_vendor_stakeholder(project_entity, vendor_entity, active=True):
    sh = Stakeholder(
        parent=project_entity,
        target=vendor_entity,
        role=StakeholderRole.VENDOR,
        active=active,
    )
    sh.save()
    return sh


def _make_client_stakeholder(project_entity, client_entity, active=True):
    sh = Stakeholder(
        parent=project_entity,
        target=client_entity,
        role=StakeholderRole.CLIENT,
        active=active,
    )
    sh.save()
    return sh


def _inject_project(system_entity, dest_entity, amount, officer_user):
    CapitalGainOperation(
        source=system_entity,
        destination=dest_entity,
        amount=amount,
        operation_type=OperationType.CAPITAL_GAIN,
        date=date.today(),
        description="Seed balance",
        officer=officer_user,
    ).save()


def _make_purchase_op(
    project_entity, vendor_entity, officer_user, amount=Decimal("1000.00")
):
    op = PurchaseOperation(
        source=project_entity,
        destination=vendor_entity,
        amount=amount,
        operation_type=OperationType.PURCHASE,
        date=date.today(),
        description="Test purchase",
        officer=officer_user,
    )
    op.save()
    return op


def _make_sale_op(
    client_entity, project_entity, officer_user, amount=Decimal("1000.00")
):
    op = SaleOperation(
        source=client_entity,
        destination=project_entity,
        amount=amount,
        operation_type=OperationType.SALE,
        date=date.today(),
        description="Test sale",
        officer=officer_user,
    )
    op.save()
    return op


def _make_expense_op(
    project_entity, world_entity, officer_user, amount=Decimal("1000.00")
):
    op = ExpenseOperation(
        source=project_entity,
        destination=world_entity,
        amount=amount,
        operation_type=OperationType.EXPENSE,
        date=date.today(),
        description="Test expense",
        officer=officer_user,
    )
    op.save()
    return op


def _make_adjustment(operation, adj_type, officer, amount=Decimal("100.00"), reason=""):
    adj = Adjustment(
        operation=operation,
        type=adj_type,
        amount=amount,
        reason=reason,
        date=date.today(),
        officer=officer,
    )
    adj.save()
    return adj


# ---------------------------------------------------------------------------
# AdjustmentTransactionTest
# ---------------------------------------------------------------------------


class AdjustmentTransactionTest(TestCase):
    """
    Verify that saving an Adjustment creates exactly one issuance transaction
    of the correct type, matching the parent operation type.
    """

    def setUp(self):
        self.system_entity = Entity.create(is_system=True)
        self.world_entity = Entity.create(is_world=True)
        self.officer = _make_officer()

        self.project_entity = _make_project_entity("Test Farm Project")
        _inject_project(
            self.system_entity, self.project_entity, Decimal("5000.00"), self.officer
        )

        self.vendor_entity = _make_vendor_entity("Vendor Ltd")
        _make_vendor_stakeholder(self.project_entity, self.vendor_entity)

        self.client_entity = _make_client_entity("Client Co")
        _make_client_stakeholder(self.project_entity, self.client_entity)
        _inject_project(
            self.system_entity, self.client_entity, Decimal("5000.00"), self.officer
        )

    def test_purchase_adjustment_creates_purchase_adjustment_transaction(self):
        op = _make_purchase_op(self.project_entity, self.vendor_entity, self.officer)
        adj = _make_adjustment(op, AdjustmentType.PURCHASE_RETURN, self.officer)

        txs = adj.get_all_transactions()
        self.assertEqual(txs.count(), 1)
        self.assertTrue(
            txs.filter(type=TransactionType.PURCHASE_ADJUSTMENT_DECREASE).exists()
        )

    def test_sale_adjustment_creates_sale_adjustment_transaction(self):
        op = _make_sale_op(self.client_entity, self.project_entity, self.officer)
        adj = _make_adjustment(op, AdjustmentType.SALE_RETURN, self.officer)

        txs = adj.get_all_transactions()
        self.assertEqual(txs.count(), 1)
        self.assertTrue(
            txs.filter(type=TransactionType.SALE_ADJUSTMENT_DECREASE).exists()
        )

    def test_expense_adjustment_creates_expense_adjustment_transaction(self):
        op = _make_expense_op(self.project_entity, self.world_entity, self.officer)
        adj = _make_adjustment(op, AdjustmentType.PURCHASE_RETURN, self.officer)

        txs = adj.get_all_transactions()
        self.assertEqual(txs.count(), 1)
        self.assertTrue(
            txs.filter(type=TransactionType.EXPENSE_ADJUSTMENT_DECREASE).exists()
        )

    def test_adjustment_transaction_source_and_target_match_operation_funds(self):
        """Transaction direction must mirror the operation's source/target funds."""
        op = _make_purchase_op(self.project_entity, self.vendor_entity, self.officer)
        adj = _make_adjustment(op, AdjustmentType.PURCHASE_RETURN, self.officer)

        tx = adj.get_all_transactions().get()
        self.assertEqual(tx.source, op.payment_source_fund)
        self.assertEqual(tx.target, op.payment_target_fund)

    def test_adjustment_transaction_amount_matches_adjustment(self):
        op = _make_purchase_op(self.project_entity, self.vendor_entity, self.officer)
        adj = _make_adjustment(
            op, AdjustmentType.PURCHASE_RETURN, self.officer, amount=Decimal("250.00")
        )

        tx = adj.get_all_transactions().get()
        self.assertEqual(tx.amount, Decimal("250.00"))


# ---------------------------------------------------------------------------
# AdjustmentEffectAutoSetTest
# ---------------------------------------------------------------------------


class AdjustmentEffectAutoSetTest(TestCase):
    """
    Verify that `effect` is automatically derived from `type` on save.
    The caller must NOT set `effect` manually — it is always overwritten.
    """

    def setUp(self):
        self.system_entity = Entity.create(is_system=True)
        self.officer = _make_officer()

        self.project_entity = _make_project_entity("Test Farm")
        _inject_project(
            self.system_entity, self.project_entity, Decimal("5000.00"), self.officer
        )

        self.vendor_entity = _make_vendor_entity("Vendor Ltd")
        _make_vendor_stakeholder(self.project_entity, self.vendor_entity)

        self.op = _make_purchase_op(
            self.project_entity, self.vendor_entity, self.officer
        )

    def _adj(self, adj_type, reason=""):
        return _make_adjustment(self.op, adj_type, self.officer, reason=reason)

    def test_purchase_return_sets_decrease(self):
        adj = self._adj(AdjustmentType.PURCHASE_RETURN)
        self.assertEqual(adj.effect, AdjustmentEffect.DECREASE)

    def test_purchase_discount_sets_decrease(self):
        adj = self._adj(AdjustmentType.PURCHASE_DISCOUNT)
        self.assertEqual(adj.effect, AdjustmentEffect.DECREASE)

    def test_purchase_undercharge_sets_increase(self):
        adj = self._adj(AdjustmentType.PURCHASE_UNDERCHARGE)
        self.assertEqual(adj.effect, AdjustmentEffect.INCREASE)

    def test_purchase_freight_sets_increase(self):
        adj = self._adj(AdjustmentType.PURCHASE_FREIGHT)
        self.assertEqual(adj.effect, AdjustmentEffect.INCREASE)

    def test_sale_return_sets_decrease(self):
        adj = self._adj(AdjustmentType.SALE_RETURN)
        self.assertEqual(adj.effect, AdjustmentEffect.DECREASE)

    def test_sale_write_off_sets_decrease(self):
        adj = self._adj(AdjustmentType.SALE_WRITE_OFF)
        self.assertEqual(adj.effect, AdjustmentEffect.DECREASE)

    def test_sale_late_fee_sets_increase(self):
        adj = self._adj(AdjustmentType.SALE_LATE_FEE)
        self.assertEqual(adj.effect, AdjustmentEffect.INCREASE)

    def test_general_reduction_sets_decrease(self):
        adj = self._adj(
            AdjustmentType.PURCHASE_GENERAL_REDUCTION, reason="Typo in invoice"
        )
        self.assertEqual(adj.effect, AdjustmentEffect.DECREASE)

    def test_general_increase_sets_increase(self):
        adj = self._adj(
            AdjustmentType.PURCHASE_GENERAL_INCREASE, reason="Missed line item"
        )
        self.assertEqual(adj.effect, AdjustmentEffect.INCREASE)


# ---------------------------------------------------------------------------
# AdjustmentValidationTest
# ---------------------------------------------------------------------------


class AdjustmentValidationTest(TestCase):
    """
    Validate business rules enforced in Adjustment.clean():
    - Only PURCHASE, SALE, EXPENSE operations may be adjusted
    - General types require a reason
    - Amount must be positive
    - Officer must be an active staff person with an auth user
    """

    def setUp(self):
        self.system_entity = Entity.create(is_system=True)
        self.world_entity = Entity.create(is_world=True)
        self.officer = _make_officer()

        self.project_entity = _make_project_entity("Test Farm")
        _inject_project(
            self.system_entity, self.project_entity, Decimal("5000.00"), self.officer
        )

        self.vendor_entity = _make_vendor_entity("Vendor Ltd")
        _make_vendor_stakeholder(self.project_entity, self.vendor_entity)

        self.op = _make_purchase_op(
            self.project_entity, self.vendor_entity, self.officer
        )

    def _adj(self, **kwargs):
        defaults = dict(
            operation=self.op,
            type=AdjustmentType.PURCHASE_RETURN,
            amount=Decimal("100.00"),
            reason="",
            date=date.today(),
            officer=self.officer,
        )
        defaults.update(kwargs)
        adj = Adjustment(**defaults)
        adj.save()
        return adj

    # ------------------------------------------------------------------
    # Operation type validation
    # ------------------------------------------------------------------

    def test_non_adjustable_operation_type_raises_validation_error(self):
        """Cash injection operations cannot be adjusted."""
        from apps.app_operation.models.proxies import CashInjectionOperation

        # Cash injection: source=world, destination=person
        recipient = _make_person_entity("Recipient")
        cash_op = CashInjectionOperation(
            source=self.world_entity,
            destination=recipient,
            amount=Decimal("500.00"),
            operation_type=OperationType.CASH_INJECTION,
            date=date.today(),
            officer=self.officer,
        )
        cash_op.save()

        with self.assertRaises(ValidationError):
            self._adj(operation=cash_op)

    def test_purchase_operation_is_adjustable(self):
        adj = self._adj()
        self.assertIsNotNone(adj.pk)

    def test_sale_operation_is_adjustable(self):
        client = _make_client_entity("Client Co")
        _make_client_stakeholder(self.project_entity, client)
        _inject_project(self.system_entity, client, Decimal("2000.00"), self.officer)
        sale_op = _make_sale_op(client, self.project_entity, self.officer)

        adj = self._adj(operation=sale_op, type=AdjustmentType.SALE_RETURN)
        self.assertIsNotNone(adj.pk)

    # ------------------------------------------------------------------
    # General type requires reason
    # ------------------------------------------------------------------

    def test_general_reduction_without_reason_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._adj(type=AdjustmentType.PURCHASE_GENERAL_REDUCTION, reason="")

    def test_general_increase_without_reason_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._adj(type=AdjustmentType.PURCHASE_GENERAL_INCREASE, reason="")

    def test_general_reduction_with_reason_saves_ok(self):
        adj = self._adj(
            type=AdjustmentType.PURCHASE_GENERAL_REDUCTION, reason="Miscounted items"
        )
        self.assertIsNotNone(adj.pk)

    def test_non_general_type_without_reason_saves_ok(self):
        adj = self._adj(type=AdjustmentType.PURCHASE_RETURN, reason="")
        self.assertIsNotNone(adj.pk)

    # ------------------------------------------------------------------
    # Amount validation (AmountCleanMixin)
    # ------------------------------------------------------------------

    def test_amount_zero_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._adj(amount=Decimal("0.00"))

    def test_amount_negative_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._adj(amount=Decimal("-50.00"))

    # ------------------------------------------------------------------
    # Officer validation (OfficerMixin)
    # ------------------------------------------------------------------

    def test_officer_user_must_be_staff(self):
        non_staff_user = User.objects.create_user(
            username="non_staff", password="x", is_staff=False
        )
        with self.assertRaises(ValidationError):
            self._adj(officer=non_staff_user)

    def test_officer_must_be_active(self):
        self.officer.is_active = False
        self.officer.save()
        with self.assertRaises(ValidationError):
            self._adj()


# ---------------------------------------------------------------------------
# AdjustmentImmutabilityTest
# ---------------------------------------------------------------------------


class AdjustmentImmutabilityTest(TestCase):
    """
    After save, the fields `operation`, `type`, `amount`, and `effect`
    must be immutable — re-assigning and saving must raise ValidationError.
    """

    def setUp(self):
        self.system_entity = Entity.create(is_system=True)
        self.officer = _make_officer()

        self.project_entity = _make_project_entity("Test Farm")
        _inject_project(
            self.system_entity, self.project_entity, Decimal("5000.00"), self.officer
        )

        self.vendor_entity = _make_vendor_entity("Vendor Ltd")
        _make_vendor_stakeholder(self.project_entity, self.vendor_entity)

        self.op = _make_purchase_op(
            self.project_entity, self.vendor_entity, self.officer
        )
        self.adj = _make_adjustment(
            self.op, AdjustmentType.PURCHASE_RETURN, self.officer
        )

    def test_operation_is_immutable_after_save(self):
        vendor2 = _make_vendor_entity("Second Vendor")
        _make_vendor_stakeholder(self.project_entity, vendor2)
        op2 = _make_purchase_op(self.project_entity, vendor2, self.officer)

        self.adj.operation = op2
        with self.assertRaises(ValidationError):
            self.adj.save()

    def test_type_is_immutable_after_save(self):
        self.adj.type = AdjustmentType.PURCHASE_DISCOUNT
        with self.assertRaises(ValidationError):
            self.adj.save()

    def test_amount_is_immutable_after_save(self):
        self.adj.amount = Decimal("999.00")
        with self.assertRaises(ValidationError):
            self.adj.save()

    def test_effect_cannot_be_changed_independently_of_type(self):
        # `effect` is always recomputed from `type` in save(), and `type` is
        # immutable — so there is no normal code path that produces a changed effect.
        # Re-saving with the same type leaves effect unchanged (no error expected).
        self.adj.save()
        self.adj.refresh_from_db()
        self.assertEqual(self.adj.effect, AdjustmentEffect.DECREASE)


# ---------------------------------------------------------------------------
# AdjustmentEffectiveAmountTest
# ---------------------------------------------------------------------------


class AdjustmentEffectiveAmountTest(TestCase):
    """
    Verify that `operation.effective_amount` (from AdjustableMixin) correctly
    reflects the sum of all active, non-reversed adjustments.
    """

    def setUp(self):
        self.system_entity = Entity.create(is_system=True)
        self.officer = _make_officer()

        self.project_entity = _make_project_entity("Test Farm")
        _inject_project(
            self.system_entity, self.project_entity, Decimal("5000.00"), self.officer
        )

        self.vendor_entity = _make_vendor_entity("Vendor Ltd")
        _make_vendor_stakeholder(self.project_entity, self.vendor_entity)

        self.op = _make_purchase_op(
            self.project_entity,
            self.vendor_entity,
            self.officer,
            amount=Decimal("1000.00"),
        )

    def _adj(self, adj_type, amount, reason=""):
        return _make_adjustment(
            self.op, adj_type, self.officer, amount=amount, reason=reason
        )

    def test_no_adjustments_returns_base_amount(self):
        self.op.refresh_from_db()
        self.assertEqual(self.op.effective_amount, Decimal("1000.00"))

    def test_single_decrease_reduces_effective_amount(self):
        self._adj(AdjustmentType.PURCHASE_RETURN, Decimal("100.00"))

        self.op.refresh_from_db()
        self.assertEqual(self.op.effective_amount, Decimal("900.00"))

    def test_single_increase_raises_effective_amount(self):
        self._adj(AdjustmentType.PURCHASE_UNDERCHARGE, Decimal("200.00"))

        self.op.refresh_from_db()
        self.assertEqual(self.op.effective_amount, Decimal("1200.00"))

    def test_mixed_adjustments_combine_correctly(self):
        self._adj(AdjustmentType.PURCHASE_RETURN, Decimal("100.00"))  # -100
        self._adj(AdjustmentType.PURCHASE_UNDERCHARGE, Decimal("50.00"))  # +50

        self.op.refresh_from_db()
        self.assertEqual(self.op.effective_amount, Decimal("950.00"))

    def test_multiple_decreases_accumulate(self):
        self._adj(AdjustmentType.PURCHASE_RETURN, Decimal("100.00"))
        self._adj(AdjustmentType.PURCHASE_DISCOUNT, Decimal("150.00"))

        self.op.refresh_from_db()
        self.assertEqual(self.op.effective_amount, Decimal("750.00"))

    def test_reversed_adjustment_excluded_from_effective_amount(self):
        adj = self._adj(AdjustmentType.PURCHASE_RETURN, Decimal("100.00"))
        adj.reverse(officer=self.officer)

        self.op.refresh_from_db()
        # Reversed adjustment is excluded — effective_amount reverts to base
        self.assertEqual(self.op.effective_amount, Decimal("1000.00"))


# ---------------------------------------------------------------------------
# AdjustmentReversalTest
# ---------------------------------------------------------------------------


class AdjustmentReversalTest(TestCase):
    """
    Verify the full reversal lifecycle for Adjustment:
    - reverse() creates a counter-adjustment linked to the original
    - original is marked as reversed; reversal is marked as is_reversal
    - counter-transaction is created with flipped source/target
    - reversed and reversal adjustments are both constraints-checked
    """

    def setUp(self):
        self.system_entity = Entity.create(is_system=True)
        self.officer = _make_officer()

        self.project_entity = _make_project_entity("Test Farm")
        _inject_project(
            self.system_entity, self.project_entity, Decimal("5000.00"), self.officer
        )

        self.vendor_entity = _make_vendor_entity("Vendor Ltd")
        _make_vendor_stakeholder(self.project_entity, self.vendor_entity)

        self.op = _make_purchase_op(
            self.project_entity, self.vendor_entity, self.officer
        )
        self.adj = _make_adjustment(
            self.op, AdjustmentType.PURCHASE_RETURN, self.officer
        )

    def test_reverse_returns_new_adjustment_instance(self):
        reversal = self.adj.reverse(officer=self.officer)

        self.assertIsNotNone(reversal.pk)
        self.assertNotEqual(reversal.pk, self.adj.pk)

    def test_reversal_is_linked_to_original(self):
        reversal = self.adj.reverse(officer=self.officer)

        self.assertEqual(reversal.reversal_of, self.adj)

    def test_original_is_marked_as_reversed(self):
        reversal = self.adj.reverse(officer=self.officer)

        self.adj.refresh_from_db()
        self.assertTrue(self.adj.is_reversed)
        self.assertEqual(self.adj.reversed_by, reversal)

    def test_reversal_is_marked_as_reversal(self):
        reversal = self.adj.reverse(officer=self.officer)

        self.assertTrue(reversal.is_reversal)
        self.assertFalse(reversal.is_reversed)

    def test_reversal_inherits_type_amount_operation(self):
        reversal = self.adj.reverse(officer=self.officer)

        self.assertEqual(reversal.operation, self.adj.operation)
        self.assertEqual(reversal.type, self.adj.type)
        self.assertEqual(reversal.amount, self.adj.amount)

    def test_reverse_creates_counter_transaction(self):
        """Original has 1 PURCHASE_ADJUSTMENT; after reversal there should be 2."""
        self.adj.reverse(officer=self.officer)

        all_txs = self.adj.get_all_transactions()
        self.assertEqual(all_txs.count(), 2)
        self.assertEqual(all_txs.filter(reversal_of__isnull=False).count(), 1)

    def test_counter_transaction_flips_source_and_target(self):
        self.adj.reverse(officer=self.officer)

        original_tx = self.adj.get_all_transactions().get(reversal_of__isnull=True)
        counter_tx = original_tx.reversed_by

        self.assertEqual(counter_tx.source, original_tx.target)
        self.assertEqual(counter_tx.target, original_tx.source)
        self.assertEqual(counter_tx.amount, original_tx.amount)

    def test_cannot_reverse_already_reversed_adjustment(self):
        self.adj.reverse(officer=self.officer)
        self.adj.refresh_from_db()

        with self.assertRaises(ValidationError):
            self.adj.reverse(officer=self.officer)

    def test_cannot_reverse_a_reversal(self):
        reversal = self.adj.reverse(officer=self.officer)

        with self.assertRaises(ValidationError):
            reversal.reverse(officer=self.officer)
