"""Tests for :class:`apps.app_base.managers.ActiveManager` and
:class:`apps.app_base.managers.SafeQuerySet`, exercised through the concrete
:class:`apps.app_entity.models.Entity` model.
"""

from django.db import models
from django.test import TestCase

from apps.app_base.managers import ActiveManager
from apps.app_entity.models import Entity, EntityType

from .general import make_entity


class ActiveManagerTests(TestCase):
    """Test ActiveManager excludes soft-deleted items.

    ``Entity.objects`` uses :class:`ActiveManager`, which filters
    ``deleted_at__isnull=True``; ``Entity.all_objects`` is the unfiltered
    manager and must keep soft-deleted rows reachable. Soft-deleted rows are
    produced through the real ``delete()`` path, which always soft-deletes.
    """

    def setUp(self):
        self.live = make_entity("ActiveEntity")
        self.removed = make_entity("SoftDeletedEntity")
        self.removed.delete()  # always soft-deletes: stamps deleted_at

    # --- manager wiring -------------------------------------------------- #

    def test_objects_manager_is_active_manager(self):
        """The ``objects`` manager should be an ActiveManager instance."""
        self.assertIsInstance(Entity.objects, ActiveManager)

    def test_all_objects_is_a_plain_manager(self):
        """``all_objects`` should be a plain (unfiltered) Manager, not ActiveManager."""
        self.assertIsInstance(Entity.all_objects, models.Manager)
        self.assertNotIsInstance(Entity.all_objects, ActiveManager)

    # --- default ``objects`` manager (active rows only) ------------------- #

    def test_objects_returns_live_rows(self):
        """``objects`` should expose non-soft-deleted rows."""
        self.assertEqual(Entity.objects.count(), 1)
        self.assertEqual(list(Entity.objects.all()), [self.live])

    def test_objects_excludes_soft_deleted(self):
        """Soft-deleted rows should never appear via the default manager."""
        self.assertNotIn(self.removed, Entity.objects.all())
        self.assertFalse(Entity.objects.filter(pk=self.removed.pk).exists())
        with self.assertRaises(Entity.DoesNotExist):
            Entity.objects.get(pk=self.removed.pk)

    def test_objects_filter_ignores_soft_deleted(self):
        """filter() through the default manager should still exclude deleted rows."""
        qs = Entity.objects.filter(name=self.removed.name)
        self.assertEqual(qs.count(), 0)
        self.assertFalse(qs.exists())
        self.assertEqual(list(qs), [])

    def test_objects_get_works_for_live_row(self):
        """get() through the default manager should resolve live rows."""
        self.assertEqual(Entity.objects.get(pk=self.live.pk), self.live)

    # --- ``all_objects`` manager (everything, incl. soft-deleted) --------- #

    def test_all_objects_returns_everything(self):
        """``all_objects`` should return live and soft-deleted rows together."""
        self.assertEqual(Entity.all_objects.count(), 2)
        self.assertEqual(
            set(
                Entity.all_objects.filter(
                    name__in=[self.live.name, self.removed.name]
                )
            ),
            {self.live, self.removed},
        )

    def test_all_objects_includes_soft_deleted(self):
        """Soft-deleted rows must stay reachable through ``all_objects``."""
        fetched = Entity.all_objects.get(pk=self.removed.pk)
        self.assertIsNotNone(fetched.deleted_at)
        self.assertIn(self.removed, Entity.all_objects.all())

    def test_all_objects_filter_includes_soft_deleted(self):
        """filter() through ``all_objects`` should still match deleted rows."""
        qs = Entity.all_objects.filter(name=self.removed.name)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(list(qs), [self.removed])

    # --- toggling the soft-delete marker ---------------------------------- #

    def test_restoring_deleted_at_returns_row_to_objects(self):
        """Clearing ``deleted_at`` should make the row visible via ``objects`` again."""
        self.removed.deleted_at = None
        self.removed.save()
        self.assertEqual(Entity.objects.count(), 2)
        self.assertIn(self.removed, Entity.objects.all())

    def test_multiple_soft_deleted_rows_all_excluded(self):
        """Soft-deleting every row should empty the default manager."""
        self.live.delete()
        self.assertEqual(Entity.objects.count(), 0)
        self.assertEqual(Entity.all_objects.count(), 2)
        self.assertEqual(
            Entity.all_objects.filter(deleted_at__isnull=True).count(), 0
        )


class SafeQuerySetTests(TestCase):
    """Test SafeQuerySet restrictions on bulk operations"""

    def test_direct_update_is_blocked(self):
        """QuerySet.update() should raise NotImplementedError"""
        entity = make_entity("Test")

        with self.assertRaises(NotImplementedError):
            Entity.objects.filter(pk=entity.pk).update(active=False)

    def test_bulk_create_is_blocked(self):
        """QuerySet.bulk_create() should raise NotImplementedError"""
        entities = [Entity(name=f"Entity{i}", entity_type=EntityType.PERSON) for i in range(3)]

        with self.assertRaises(NotImplementedError):
            Entity.objects.bulk_create(entities)
