"""
Soft-delete + unique-reuse tests.

Covers the conditional (partial) unique indexes that scope uniqueness to live
rows only (``deleted_at IS NULL``), so a soft-deleted row no longer keeps its
unique value "taken" forever. A live duplicate is still rejected with a
friendly ``ValidationError``.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType
from apps.app_entity.models.category import (
    FinancialCategoriesEntitiesRelations,
    FinancialCategory,
)


class EntityNameReuseAfterSoftDeleteTests(TestCase):
    """Entity.name uniqueness is scoped to live rows only."""

    def test_soft_deleted_name_can_be_reused(self):
        first = Entity.create(EntityType.PERSON, name="Reusable Name")
        first.delete()  # soft-delete: stamps deleted_at, keeps the row

        # Re-creating with the same name must not collide with the tombstone.
        second = Entity.create(EntityType.PERSON, name="Reusable Name")
        self.assertIsNotNone(second.pk)
        self.assertNotEqual(first.pk, second.pk)
        # Tombstone + one live row share the name; only the live one is visible.
        self.assertEqual(Entity.all_objects.filter(name="Reusable Name").count(), 2)
        self.assertEqual(Entity.objects.filter(name="Reusable Name").count(), 1)

    def test_live_duplicate_name_still_rejected(self):
        """Two LIVE entities still cannot share a name (friendly error)."""
        Entity.create(EntityType.PERSON, name="Live Duplicate")
        with self.assertRaises(ValidationError):
            Entity.create(EntityType.PERSON, name="Live Duplicate")


class FinancialCategoryUniqueReuseTests(TestCase):
    """FinancialCategory.name uniqueness is scoped to live rows only."""

    def _create_category(self, name):
        return FinancialCategory.objects.create(
            name=name, aspect="General", category_type="EXPENSE"
        )

    def test_soft_deleted_category_name_can_be_reused(self):
        first = self._create_category("Soft-Reusable Expense")
        first.delete()

        second = self._create_category("Soft-Reusable Expense")
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(
            FinancialCategory.all_objects.filter(
                name="Soft-Reusable Expense"
            ).count(),
            2,
        )
        self.assertEqual(
            FinancialCategory.objects.filter(name="Soft-Reusable Expense").count(),
            1,
        )

    def test_live_duplicate_category_name_still_rejected(self):
        self._create_category("Live Category Duplicate")
        with self.assertRaises(ValidationError):
            self._create_category("Live Category Duplicate")


class EntityCategoryRelationUniqueReuseTests(TestCase):
    """(entity, category) relation uniqueness is scoped to live rows only."""

    def setUp(self):
        self.entity = Entity.create(EntityType.PROJECT, name="Relation Project")
        self.category = FinancialCategory.objects.create(
            name="Relation Expense", aspect="General", category_type="EXPENSE"
        )

    def test_soft_deleted_relation_can_be_recreated(self):
        relation = FinancialCategoriesEntitiesRelations.objects.create(
            entity=self.entity, category=self.category
        )
        relation.delete()

        recreated = FinancialCategoriesEntitiesRelations.objects.create(
            entity=self.entity, category=self.category
        )
        self.assertNotEqual(relation.pk, recreated.pk)
        self.assertEqual(
            FinancialCategoriesEntitiesRelations.all_objects.filter(
                entity=self.entity, category=self.category
            ).count(),
            2,
        )
        self.assertEqual(
            FinancialCategoriesEntitiesRelations.objects.filter(
                entity=self.entity, category=self.category
            ).count(),
            1,
        )

    def test_live_duplicate_relation_still_rejected(self):
        FinancialCategoriesEntitiesRelations.objects.create(
            entity=self.entity, category=self.category
        )
        with self.assertRaises(ValidationError):
            FinancialCategoriesEntitiesRelations.objects.create(
                entity=self.entity, category=self.category
            )
