"""
Tests for ``manage.py clean`` — the hard-delete purge of accumulated
soft-deleted rows.
"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType
from apps.app_operation.models.period import FinancialPeriod


def _person(name):
    """A normal person entity — auto-creates an open financial period."""
    return Entity.create(EntityType.PERSON, name=name)


class CleanCommandTests(TestCase):
    def test_purges_soft_deleted_rows_and_keeps_live(self):
        doomed = _person("Doomed")
        period = doomed.financial_periods.get()
        doomed.delete()  # soft delete: entity + its auto-created period -> tombstones
        live = _person("Live")

        call_command("clean", stdout=StringIO())

        # Tombstones physically removed (period first, then the entity that the
        # period tombstone referenced).
        self.assertFalse(Entity.all_objects.filter(pk=doomed.pk).exists())
        self.assertFalse(FinancialPeriod.all_objects.filter(pk=period.pk).exists())
        # Live rows are untouched.
        self.assertTrue(Entity.all_objects.filter(pk=live.pk).exists())
        self.assertIsNone(Entity.objects.get(pk=live.pk).deleted_at)

    def test_dry_run_removes_nothing(self):
        doomed = _person("Doomed dry")
        doomed.delete()

        call_command("clean", dry_run=True, stdout=StringIO())

        self.assertTrue(Entity.all_objects.filter(pk=doomed.pk).exists())

    def test_older_than_skips_recent_tombstones(self):
        doomed = _person("Recent tombstone")
        doomed.delete()

        call_command("clean", older_than=30, stdout=StringIO())

        self.assertTrue(Entity.all_objects.filter(pk=doomed.pk).exists())

    def test_model_filter_leaves_referenced_tombstone(self):
        doomed = _person("Referenced tombstone")
        period = doomed.financial_periods.get()
        doomed.delete()  # the period tombstone still references the entity tombstone

        call_command("clean", model="app_entity.Entity", stdout=StringIO())

        # The entity tombstone is still referenced (PROTECT) by its period
        # tombstone, which is not a candidate in this --model run — both remain.
        self.assertTrue(Entity.all_objects.filter(pk=doomed.pk).exists())
        self.assertTrue(FinancialPeriod.all_objects.filter(pk=period.pk).exists())
