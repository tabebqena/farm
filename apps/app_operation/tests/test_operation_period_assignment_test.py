from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import QuerySet as DjangoQuerySet
from django.test import TestCase
from apps.app_entity.models import Entity, EntityType
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.period import FinancialPeriod
from apps.app_operation.models.proxies import CashInjectionOperation

User = get_user_model()

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)
LAST_MONTH = TODAY - timedelta(days=30)
NEXT_MONTH = TODAY + timedelta(days=30)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_officer():
    return User.objects.create_user(username="officer_fp", password="x", is_staff=True)


def _make_person_entity(name="Receiver"):
    return Entity.create(EntityType.PERSON, name=name)


def _make_world_entity():
    return Entity.create(EntityType.WORLD)


# ---------------------------------------------------------------------------
# FinancialPeriod model tests
# ---------------------------------------------------------------------------



class OperationPeriodAssignmentTest(TestCase):
    """Tests for the auto-assign and closed-period guard on Operation."""

    def setUp(self):
        self.world_entity = _make_world_entity()
        self.officer = _make_officer()
        self.receiver = _make_person_entity("Receiver Assign")

    def _make_injection(self, **kwargs):
        defaults = dict(
            source=self.world_entity,
            destination=self.receiver,
            amount=Decimal("500.00"),
            operation_type=OperationType.CASH_INJECTION,
            date=TODAY,
            officer=self.officer,
        )
        defaults.update(kwargs)
        op = CashInjectionOperation(**defaults)
        op.save()
        return op

    def _receiver_period(self):
        return FinancialPeriod.objects.get(entity=self.receiver)

    # --- auto-assign ---

    def test_operation_gets_period_auto_assigned(self):
        op = self._make_injection()
        self.assertIsNotNone(op.period)
        self.assertEqual(op.period.entity, self.receiver)

    def test_operation_period_is_the_open_period(self):
        expected = self._receiver_period()
        op = self._make_injection()
        self.assertEqual(op.period, expected)

    # --- auto-create period when none is open ---

    def test_operation_assigned_to_auto_created_period_after_close(self):
        period = self._receiver_period()
        # close() on an active entity auto-creates the next period with start_date=TOMORROW.
        period.close(TOMORROW)
        op = self._make_injection(date=TOMORROW)
        self.assertIsNotNone(op.period)
        self.assertFalse(op.period.is_closed)
        self.assertEqual(op.period.start_date, TOMORROW)

    def test_period_start_date_equals_close_date(self):
        # close() creates the next period with start_date == the closing end_date (TOMORROW).
        period = self._receiver_period()
        period.close(TOMORROW)
        op = self._make_injection(date=TOMORROW)
        self.assertEqual(op.period.start_date, TOMORROW)

    # --- closed period blocks new operation ---

    def test_operation_in_closed_period_raises(self):
        # Force the receiver's period to be truly closed (end_date in the past).
        # DjangoQuerySet.update bypasses the SafeQuerySet override for test setup only.
        period = self._receiver_period()
        DjangoQuerySet.update(
            FinancialPeriod.all_objects.filter(pk=period.pk),
            start_date=LAST_MONTH,
            end_date=YESTERDAY,
        )
        period.refresh_from_db()
        # Create an open period from YESTERDAY so the entity remains active.
        FinancialPeriod(entity=self.receiver, start_date=YESTERDAY).save()
        # An op dated within the closed period [LAST_MONTH, YESTERDAY) must be rejected.
        with self.assertRaises(ValidationError):
            self._make_injection(date=LAST_MONTH)

    def test_operation_in_period_with_future_end_date_allowed(self):
        # A period whose end_date is in the future is still open; operations must not be blocked.
        period = self._receiver_period()
        period.close(TOMORROW)  # end_date=TOMORROW → open by definition
        op = self._make_injection(date=TODAY)
        assert op.period is not None
        self.assertFalse(op.period.is_closed)

    def test_operation_before_any_period_is_not_allowed(self):
        """
        A date that falls before the entity's period start is not in any closed
        period, so the operation should fail.
        """
        period = self._receiver_period()
        before_start = period.start_date - timedelta(days=5)
        # The receiver has one open period starting today; its start may equal today.
        # A date in the past before any period is fine — no closed period covers it.
        with self.assertRaises(ValidationError):
            op = self._make_injection(date=before_start)

    def test_operation_raises_when_no_open_period(self):
        """With an inactive entity, close() creates no next period; the following operation must fail."""
        self.receiver.active = False
        self.receiver.save()
        period = self._receiver_period()
        period.close(TOMORROW)  # inactive entity → no next period created
        with self.assertRaises(ValidationError):
            self._make_injection(date=TOMORROW)

    # --- reversal is not blocked by closed period ---

    def test_reversal_not_blocked_by_closed_period(self):
        op = self._make_injection()
        period = self._receiver_period()
        # Force-close the period in the past (DjangoQuerySet.update bypasses SafeQuerySet).
        DjangoQuerySet.update(
            FinancialPeriod.all_objects.filter(pk=period.pk),
            start_date=LAST_MONTH,
            end_date=YESTERDAY,
        )
        period.refresh_from_db()
        # Create an open period so the reversal has somewhere to land.
        FinancialPeriod(entity=self.receiver, start_date=YESTERDAY).save()
        # Reversals must not be blocked even when the original op's period is now closed.
        reversal = op.reverse(officer=self.officer)
        self.assertIsNotNone(reversal.pk)

    # --- period_entity resolves correctly for CashInjection ---

    def test_period_entity_is_destination_for_cash_injection(self):
        op = self._make_injection()
        # CashInjection: _source_role="world", _dest_role="url"
        self.assertEqual(op.period_entity, self.receiver)
