from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import DeathOperation

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


def _make_project_entity(name):
    project = Entity.create(EntityType.PROJECT, name=name)
    return project


def _make_system_entity():
    return Entity.create(EntityType.SYSTEM)


# ---------------------------------------------------------------------------
# DeathCreateTest
# ---------------------------------------------------------------------------


class DeathCreateTest(TestCase):
    """
    Tests for death operation creation: config, validation, and the
    auto-settled issuance + payment transactions.

    A death removes an existing Animal/Batch from active inventory with no
    cash flow — the project's asset value is written off to the system entity.
    """

    def setUp(self):
        self.system_entity = _make_system_entity()
        self.officer_user = _make_officer()

        self.project_entity = _make_project_entity("Test Farm Project")

    def _make_op(self, **kwargs):
        defaults = dict(
            source=self.project_entity,
            destination=self.system_entity,
            amount=Decimal("500.00"),
            operation_type=OperationType.DEATH,
            date=date.today(),
            description="Test death",
            officer=self.officer_user,
        )
        defaults.update(kwargs)
        return DeathOperation(**defaults)

    # ------------------------------------------------------------------
    # Config flags
    # ------------------------------------------------------------------

    def test_has_category_config_is_false(self):
        self.assertFalse(DeathOperation.has_category)

    def test_category_required_config_is_false(self):
        self.assertFalse(DeathOperation.category_required)

    def test_can_pay_config_is_false(self):
        self.assertFalse(DeathOperation.can_pay)

    def test_is_one_shot_operation_config_is_false(self):
        """No payment mixin → the one-shot flag is not set for Death."""
        self.assertFalse(DeathOperation._is_one_shot_operation)

    def test_is_partially_payable_config_is_false(self):
        self.assertFalse(DeathOperation.is_partially_payable)

    # ------------------------------------------------------------------
    # No accounting transactions — Death is a stock event
    # ------------------------------------------------------------------

    def test_save_creates_no_transactions(self):
        op = self._make_op()
        op.save()

        self.assertIsNotNone(op.pk)
        self.assertEqual(op.get_all_transactions().count(), 0)

    def test_period_is_assigned_and_no_settlement_machinery(self):
        op = self._make_op(amount=Decimal("500.00"))
        op.save()

        self.assertIsNotNone(op.period, "A covering financial period is assigned")
        self.assertFalse(hasattr(op, "amount_settled"))
        self.assertFalse(hasattr(op, "is_fully_settled"))
        self.assertFalse(hasattr(op, "create_payment_transaction"))

    # ------------------------------------------------------------------
    # Source validation — must be a Project entity
    # ------------------------------------------------------------------

    def test_source_must_be_a_project_entity(self):
        non_project = _make_person_entity("Not A Project")
        op = self._make_op(source=non_project)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_world_entity_raises_validation_error(self):
        world_entity = Entity.create(EntityType.WORLD)
        op = self._make_op(source=world_entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_system_entity_raises_validation_error(self):
        # The System entity already exists (setUp) — only one is allowed. Use it
        # directly as the source; clean_source must reject it (not a Project).
        op = self._make_op(source=self.system_entity, destination=self.project_entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_must_be_active(self):
        self.project_entity.active = False
        self.project_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Destination validation — must be the System entity
    # ------------------------------------------------------------------

    def test_destination_must_be_system_entity(self):
        non_system = _make_project_entity("Not The System")
        op = self._make_op(destination=non_system)
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
        op = self._make_op(amount=Decimal("-50.00"))
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Officer validation
    # ------------------------------------------------------------------

    def test_officer_must_be_a_staff_user(self):
        non_staff = User.objects.create_user(
            username="non_staff", password="testpass", is_staff=False
        )
        op = self._make_op(officer=non_staff)
        with self.assertRaises(ValidationError):
            op.save()
