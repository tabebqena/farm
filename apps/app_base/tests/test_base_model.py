"""Tests for :class:`apps.app_base.models.BaseModel`.

Covers the automatic timestamps, the soft-delete field and the ``delete()`` /
post-save dispatch semantics, exercised through the concrete
:class:`apps.app_entity.models.Entity` model.
"""

from django.test import TestCase
from django.utils import timezone

from apps.app_entity.models import Entity, EntityType

from .general import make_entity


class BaseModelTimestampTests(TestCase):
    """Test BaseModel created_at and updated_at automatic fields"""

    def test_created_at_set_automatically(self):
        """created_at should be set automatically on save"""
        before = timezone.now()
        entity = make_entity("Test Entity")
        after = timezone.now()

        self.assertIsNotNone(entity.created_at)
        self.assertGreaterEqual(entity.created_at, before)
        self.assertLessEqual(entity.created_at, after)

    def test_updated_at_set_on_creation(self):
        """updated_at should be set on new objects"""
        entity = make_entity("Test Entity")
        self.assertIsNotNone(entity.updated_at)

    def test_created_at_unchanged_on_update(self):
        """created_at should not change when object is updated"""
        entity = make_entity("Test Entity")
        original_created_at = entity.created_at

        # Change something else
        entity.active = False
        entity.save()
        entity.refresh_from_db()

        self.assertEqual(entity.created_at, original_created_at)

    def test_updated_at_changes_on_update(self):
        """updated_at should change when object is updated"""
        entity = make_entity("Test Entity")
        original_updated_at = entity.updated_at

        # Change and save
        entity.active = False
        entity.save()
        entity.refresh_from_db()

        self.assertGreaterEqual(entity.updated_at, original_updated_at)


class BaseModelSoftDeleteFieldTests(TestCase):
    """Test BaseModel soft-delete field behavior"""

    def test_deleted_at_initially_null(self):
        """deleted_at should be NULL for new objects"""
        entity = make_entity("Test Entity")
        self.assertIsNone(entity.deleted_at)


class SoftDeleteTests(TestCase):
    """delete() must always soft-delete — never physically remove a row."""

    def setUp(self):
        self.entity = make_entity("DeleteMe")

    def test_delete_stamps_deleted_at_and_keeps_row(self):
        """delete() should set deleted_at and keep the row in the table."""
        self.entity.delete()

        kept = Entity.all_objects.get(pk=self.entity.pk)
        self.assertIsNotNone(kept.deleted_at)

    def test_deleted_row_hidden_from_objects_kept_in_all_objects(self):
        """After delete(), objects excludes the row but all_objects retains it."""
        self.entity.delete()

        self.assertNotIn(self.entity, Entity.objects.all())
        self.assertFalse(Entity.objects.filter(pk=self.entity.pk).exists())
        self.assertEqual(Entity.objects.count(), 0)
        self.assertIsNotNone(Entity.all_objects.get(pk=self.entity.pk).deleted_at)

    def test_delete_is_idempotent(self):
        """Deleting an already soft-deleted row must not raise."""
        self.entity.delete()
        self.entity.delete()  # second delete is a no-op soft-delete

    def test_deleted_row_can_be_restored(self):
        """Clearing deleted_at after delete() should bring the row back."""
        self.entity.delete()

        self.entity.deleted_at = None
        self.entity.save()

        self.assertIn(self.entity, Entity.objects.all())

    def test_queryset_delete_soft_deletes_every_row(self):
        """Bulk queryset.delete() should soft-delete each row, not hard-delete."""
        other = make_entity("DeleteMeToo")
        self.assertEqual(Entity.all_objects.count(), 2)

        deleted_count, _ = Entity.all_objects.filter(
            name__in=[self.entity.name, other.name]
        ).delete()

        self.assertEqual(deleted_count, 2)
        self.assertEqual(Entity.objects.count(), 0)
        self.assertEqual(Entity.all_objects.count(), 2)
        self.assertEqual(
            Entity.all_objects.filter(deleted_at__isnull=True).count(), 0
        )


class PostSaveTaskDispatchTests(TestCase):
    """Test BaseModel.post_save() task execution"""

    def test_post_save_tasks_are_executed(self):
        """post_save_tasks should be executed after save"""
        executed = []

        def dummy_task(arg):
            executed.append(arg)

        entity = Entity(name="Test", entity_type=EntityType.PERSON)
        entity.save(post_save_tasks=[(dummy_task, ("test",), {})])

        self.assertEqual(executed, ["test"])

    def test_post_save_with_kwargs(self):
        """post_save_tasks should work with keyword arguments"""
        executed = []

        def dummy_task(arg1, arg2=None):
            executed.append((arg1, arg2))

        entity = Entity(name="Test", entity_type=EntityType.PERSON)
        entity.save(post_save_tasks=[(dummy_task, ("test",), {"arg2": "kwarg"})])

        self.assertEqual(executed, [("test", "kwarg")])
