from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import QuerySet as DjangoQuerySet
from django.test import TestCase

from apps.app_entity.models import Entity, Person, Project
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
    user = User.objects.create_user(username="officer_fp", password="x", is_staff=True)
    person = Person.create(private_name="Officer FP", auth_user=user)
    return person.entity


def _make_person_entity(name="Receiver"):
    return Person.create(private_name=name).entity


def _make_world_entity():
    return Entity.create(is_world=True)


# ---------------------------------------------------------------------------
# FinancialPeriod model tests
# ---------------------------------------------------------------------------


class FinancialPeriodModelTest(TestCase):
    def setUp(self):
        self.entity = _make_person_entity("Period Owner")

    def _get_auto_period(self):
        """Return the period that was auto-created when the entity was created."""
        return FinancialPeriod.objects.get(entity=self.entity)

    # --- basic state ---

    def test_auto_created_period_is_open(self):
        period = self._get_auto_period()
        self.assertFalse(period.is_closed)
        self.assertIsNone(period.end_date)

    def test_auto_created_period_start_date_matches_entity_creation(self):
        period = self._get_auto_period()
        self.assertEqual(period.start_date, self.entity.created_at.date())

    # --- close() ---

    def test_close_sets_end_date(self):
        period = self._get_auto_period()
        period.close(TOMORROW)
        period.refresh_from_db()
        self.assertEqual(period.end_date, TOMORROW)
        self.assertIsNotNone(period.end_date)

    def test_close_end_date_before_start_raises(self):
        period = self._get_auto_period()
        with self.assertRaises(ValidationError):
            period.close(period.start_date - timedelta(days=1))

    def test_closing_already_closed_period_raises(self):
        period = self._get_auto_period()
        period.close(TOMORROW)
        with self.assertRaises(ValidationError):
            period.close(TOMORROW)

    def test_close_returns_new_open_period_for_active_entity(self):
        period = self._get_auto_period()
        next_period = period.close(TOMORROW)
        self.assertIsNotNone(next_period)
        self.assertIsNone(next_period.end_date)
        self.assertEqual(next_period.start_date, TOMORROW)
        self.assertEqual(next_period.entity, self.entity)

    def test_close_returns_none_for_inactive_entity(self):
        period = self._get_auto_period()
        self.entity.active = False
        self.entity.save()
        result = period.close(TOMORROW)
        self.assertIsNone(result)
        self.assertEqual(FinancialPeriod.objects.filter(entity=self.entity).count(), 1)

    def test_end_date_is_immutable_once_set(self):
        period = self._get_auto_period()
        period.close(TOMORROW)
        period.refresh_from_db()
        period.end_date = TOMORROW + timedelta(days=1)
        with self.assertRaises(ValidationError):
            period.save()

    # --- start_date / entity immutability ---

    def test_start_date_is_immutable(self):
        period = self._get_auto_period()
        period.start_date = YESTERDAY
        with self.assertRaises(ValidationError):
            period.save()

    def test_entity_is_immutable(self):
        period = self._get_auto_period()
        other = _make_person_entity("Other")
        period.entity = other
        with self.assertRaises(ValidationError):
            period.save()

    # --- overlap constraint ---

    def test_overlapping_period_same_entity_raises(self):
        period = self._get_auto_period()
        period.close(TOMORROW)
        # Try to create a period whose start is within the closed period
        overlap = FinancialPeriod(entity=self.entity, start_date=YESTERDAY)
        with self.assertRaises(ValidationError):
            overlap.save()

    def test_two_open_periods_same_entity_raises(self):
        # Entity already has an open period from auto-create.
        duplicate = FinancialPeriod(entity=self.entity, start_date=TOMORROW)
        with self.assertRaises(ValidationError):
            duplicate.save()

    def test_non_overlapping_sequential_periods_allowed(self):
        period = self._get_auto_period()
        period.close(TOMORROW, False)
        # New period starts the day after the closed one ended — no overlap.
        new_period = FinancialPeriod(entity=self.entity, start_date=TOMORROW)
        new_period.save()
        self.assertIsNotNone(new_period.pk)

    # --- is_closed boundaries ---

    def test_is_closed_false_when_end_date_is_today(self):
        # is_closed requires end_date < today; today itself is not yet past
        period = self._get_auto_period()
        period.end_date = TODAY
        self.assertFalse(period.is_closed)

    def test_is_closed_true_when_end_date_is_yesterday(self):
        period = self._get_auto_period()
        period.end_date = YESTERDAY
        self.assertTrue(period.is_closed)

    def test_is_closed_false_when_end_date_is_tomorrow(self):
        period = self._get_auto_period()
        period.end_date = TOMORROW
        self.assertFalse(period.is_closed)

    # --- cross-entity isolation ---

    def test_same_dates_different_entities_no_overlap_error(self):
        other = _make_person_entity("Other Entity")
        # Both entities have an open period starting today — must not conflict
        self.assertEqual(FinancialPeriod.objects.filter(entity=self.entity).count(), 1)
        self.assertEqual(FinancialPeriod.objects.filter(entity=other).count(), 1)


# ---------------------------------------------------------------------------
# Entity auto-period creation via signal
# ---------------------------------------------------------------------------


class EntityPeriodAutoCreateTest(TestCase):

    def test_new_person_entity_gets_period(self):
        entity = Person.create(private_name="Auto Period Person").entity
        self.assertEqual(FinancialPeriod.objects.filter(entity=entity).count(), 1)

    def test_new_project_entity_gets_period(self):
        project = Project(name="Auto Period Project")
        project.save()
        entity = Entity.create(owner=project)
        self.assertEqual(FinancialPeriod.objects.filter(entity=entity).count(), 1)

    def test_world_entity_does_not_get_period(self):
        entity = Entity.create(is_world=True)
        self.assertEqual(FinancialPeriod.objects.filter(entity=entity).count(), 0)

    def test_system_entity_does_not_get_period(self):
        entity = Entity.create(is_system=True, is_internal=True)
        self.assertEqual(FinancialPeriod.objects.filter(entity=entity).count(), 0)

    def test_period_start_date_equals_entity_creation_date(self):
        entity = Person.create(private_name="Date Check Person").entity
        period = FinancialPeriod.objects.get(entity=entity)
        self.assertEqual(period.start_date, entity.created_at.date())


# ---------------------------------------------------------------------------
# Operation period assignment and validation
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
            start_date=LAST_MONTH, end_date=YESTERDAY,
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
            start_date=LAST_MONTH, end_date=YESTERDAY,
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
