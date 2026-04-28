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
