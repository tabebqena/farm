"""Consolidated FinancialPeriod model tests."""

from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType
from apps.app_operation.models.period import FinancialPeriod

# Module-level helpers


def _make_project(name="Test Project") -> Entity:
    """Create a PROJECT entity."""
    return Entity.create(EntityType.PROJECT, name=name)


def _make_person(name="Test Person") -> Entity:
    """Create a PERSON entity."""
    return Entity.create(EntityType.PERSON, name=name)


def _make_world() -> Entity:
    """Create a WORLD entity."""
    return Entity.create(EntityType.WORLD, name="World")


def _make_system() -> Entity:
    """Create a SYSTEM entity."""
    return Entity.create(EntityType.SYSTEM, name="System")


def _close_period(
    period: FinancialPeriod, days_ahead: int = 1
) -> "tuple[date, FinancialPeriod | None]":
    """Close a period using the close() method and return (end_date, next_period)."""
    end_date = date.today() + timedelta(days=days_ahead)
    next_period = period.close(end_date)
    return end_date, next_period


# Test classes


class PeriodAutoCreateTest(TestCase):
    """Auto-creation of periods when entities are created."""

    def test_person_entity_gets_auto_created_period(self):
        """A PERSON entity auto-gets a period on creation."""
        person = _make_person("Alice")
        period = person.financial_periods.first()
        self.assertIsNotNone(period)
        self.assertEqual(period.entity, person)

    def test_project_entity_gets_auto_created_period(self):
        """A PROJECT entity auto-gets a period on creation."""
        project = _make_project("Farm")
        period = project.financial_periods.first()
        self.assertIsNotNone(period)
        self.assertEqual(period.entity, project)

    def test_world_entity_does_not_get_period(self):
        """A WORLD entity does NOT get a period."""
        world = _make_world()
        self.assertEqual(world.financial_periods.count(), 0)

    def test_system_entity_does_not_get_period(self):
        """A SYSTEM entity does NOT get a period."""
        system = _make_system()
        self.assertEqual(system.financial_periods.count(), 0)

    def test_auto_period_start_date_equals_entity_created_at(self):
        """Auto-created period start_date matches entity.created_at.date()."""
        person = _make_person("Bob")
        period = person.financial_periods.first()
        self.assertEqual(period.start_date, person.created_at.date())


class PeriodLifecycleTest(TestCase):
    """Open/close lifecycle and state transitions."""

    def setUp(self):
        self.entity = _make_project("Farm")
        self.period = self.entity.financial_periods.first()

    def test_new_period_is_open(self):
        """Newly created period has end_date=None (open)."""
        self.assertIsNone(self.period.end_date)

    def test_close_sets_end_date(self):
        """Calling close() sets end_date."""
        end_date, _ = _close_period(self.period)
        self.period.refresh_from_db()
        self.assertEqual(self.period.end_date, end_date)

    def test_close_creates_next_period_for_active_entity(self):
        """close() auto-creates next period if entity is still active."""
        end_date = date.today() + timedelta(days=1)
        next_period = self.period.close(end_date)
        self.assertIsNotNone(next_period)
        self.assertEqual(next_period.entity, self.entity)
        self.assertEqual(next_period.start_date, end_date)
        self.period.refresh_from_db()
        self.assertEqual(self.period.end_date, end_date)

    def test_close_returns_none_for_inactive_entity(self):
        """close() returns None if entity is inactive."""
        self.entity.active = False
        self.entity.save()
        next_period = self.period.close()
        self.assertIsNone(next_period)

    def test_close_already_closed_raises(self):
        """Calling close() on already-closed period raises ValidationError."""
        _close_period(self.period)
        self.period.refresh_from_db()
        with self.assertRaises(ValidationError):
            self.period.close()

    def test_close_with_end_date_before_start_raises(self):
        """close(end_date) where end_date < start_date raises."""
        bad_end = self.period.start_date - timedelta(days=1)
        with self.assertRaises(ValidationError):
            self.period.close(bad_end)

    def test_close_with_end_date_equal_start_raises(self):
        """close(end_date) where end_date == start_date raises (clean_end_date)."""
        same_day = self.period.start_date
        with self.assertRaises(ValidationError):
            self.period.close(same_day)


class PeriodImmutabilityTest(TestCase):
    """Immutability constraints via ImmutableMixin."""

    def setUp(self):
        self.entity = _make_project("Farm")
        self.period = self.entity.financial_periods.first()

    def test_entity_is_immutable(self):
        """Changing entity field raises ValidationError."""
        new_entity = _make_project("Other")
        self.period.entity = new_entity
        with self.assertRaises(ValidationError):
            self.period.save()

    def test_start_date_is_immutable(self):
        """Changing start_date raises ValidationError."""
        self.period.start_date = date.today() + timedelta(days=1)
        with self.assertRaises(ValidationError):
            self.period.save()

    def test_end_date_can_be_set_from_none(self):
        """end_date can transition from None to a date (ALLOW_SET)."""
        end_date = date.today() + timedelta(days=1)
        self.period.end_date = end_date
        self.period.save()
        self.assertEqual(self.period.end_date, end_date)

    def test_end_date_cannot_be_changed_once_set(self):
        """Once set, end_date cannot be changed."""
        # Use close() directly instead of _close_period since close() auto-creates next period
        end_date = date.today() + timedelta(days=1)
        self.period.close(end_date)

        new_date = date.today() + timedelta(days=2)
        self.period.end_date = new_date
        with self.assertRaises(ValidationError):
            self.period.save()


class PeriodValidationTest(TestCase):
    """Overlap prevention and field validation."""

    def setUp(self):
        self.entity = _make_project("Farm")
        self.period1 = self.entity.financial_periods.first()

    def test_sequential_periods_allowed(self):
        """Two sequential periods (no overlap) is allowed."""
        end1 = date.today() + timedelta(days=1)
        self.period1.end_date = end1
        self.period1.save()

        period2 = FinancialPeriod.objects.create(
            entity=self.entity,
            start_date=end1,
        )
        period2.full_clean()
        period2.save()
        self.assertIsNotNone(period2.pk)

    def test_overlapping_periods_raises(self):
        """Two overlapping periods for same entity raises."""
        # Set up first period: today to tomorrow
        self.period1.end_date = date.today() + timedelta(days=1)
        self.period1.save()

        # Try to create overlapping second period
        period2 = FinancialPeriod(
            entity=self.entity,
            start_date=date.today(),
        )
        with self.assertRaises(ValidationError):
            period2.full_clean()

    def test_two_open_periods_raises(self):
        """Two open (end_date=None) periods for same entity raises."""
        period2 = FinancialPeriod(
            entity=self.entity,
            start_date=date.today() + timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            period2.full_clean()

    def test_cannot_create_period_for_inactive_entity(self):
        """Creating a new period for an inactive entity raises."""
        self.entity.active = False
        self.entity.save()

        period = FinancialPeriod(
            entity=self.entity,
            start_date=date.today(),
        )
        with self.assertRaises(ValidationError):
            period.full_clean()


class PeriodIsClosedTest(TestCase):
    """is_closed property boundary conditions."""
