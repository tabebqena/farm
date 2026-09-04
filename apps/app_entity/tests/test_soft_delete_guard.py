"""
Soft-delete parent guard tests.

Deleting a parent that still has live dependent rows is refused with a
``ValidationError`` naming what to delete (or reverse) first — mirroring the DB
``PROTECT`` semantics under soft delete. Relations a model lists in
``_delete_auto_relations`` are soft-deleted automatically instead of blocking,
which lets a model break circular references.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import Product, ProductTemplate


def _make_entity(name, entity_type=EntityType.PERSON):
    """A normal (non-virtual) entity — auto-creates an open financial period."""
    return Entity.create(entity_type, name=name)


class EntityGuardTests(TestCase):
    """A parent with live dependents cannot be deleted until they go first."""

    def setUp(self):
        self.parent = _make_entity("Guarded Entity", EntityType.PROJECT)
        self.template = ProductTemplate.objects.create(
            name="Tagged Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            tracking_mode=ProductTemplate.TrackingMode.INDIVIDUAL,
            default_unit="Head",
            has_tag=True,
        )

    def _live_child_product(self, tag="G-1"):
        return Product.objects.create(
            product_template=self.template,
            entity=self.parent,
            unit_price=Decimal("10.00"),
            quantity=1,
            unique_id=tag,
        )

    def test_delete_blocked_while_live_child_exists(self):
        """Deleting a parent with a live (non-auto) child raises ValidationError."""
        self._live_child_product()

        with self.assertRaises(ValidationError) as ctx:
            self.parent.delete()

        message = str(ctx.exception)
        self.assertIn("cannot be deleted", message)
        self.assertIn("product", message)  # names the dependent to remove first
        self.parent.refresh_from_db()
        self.assertIsNone(self.parent.deleted_at)

    def test_auto_children_untouched_when_guard_blocks(self):
        """A failed delete must not partially soft-delete auto children."""
        child = self._live_child_product()
        period = self.parent.financial_periods.get()  # auto-created open period

        with self.assertRaises(ValidationError):
            self.parent.delete()

        period.refresh_from_db()
        self.assertIsNone(period.deleted_at)
        child.refresh_from_db()
        self.assertIsNone(child.deleted_at)

    def test_leaf_up_delete_succeeds(self):
        """Deleting the child first lets the parent be deleted."""
        child = self._live_child_product()
        child.delete()
        self.parent.delete()

        self.parent.refresh_from_db()
        self.assertIsNotNone(self.parent.deleted_at)

    def test_get_delete_blockers_lists_dependents(self):
        child = self._live_child_product()
        blockers = self.parent.get_delete_blockers()
        self.assertTrue(any("product" in b for b in blockers))
        child.delete()
        self.assertEqual(self.parent.get_delete_blockers(), [])


class EntityAutoDeleteTests(TestCase):
    """Relations in ``_delete_auto_relations`` are soft-deleted with the parent."""

    def test_auto_created_period_is_soft_deleted_with_entity(self):
        entity = _make_entity("Auto Period Entity")
        period = entity.financial_periods.get()

        entity.delete()

        period.refresh_from_db()
        self.assertIsNotNone(period.deleted_at)

    def test_owned_contact_soft_deleted_with_entity(self):
        from apps.app_entity.models import ContactInfo

        entity = _make_entity("Auto Contact Entity")
        contact = ContactInfo.objects.create(
            entity=entity,
            contact_type="email",
            value="a@b.test",
            label="work",
        )

        entity.delete()

        contact.refresh_from_db()
        self.assertIsNotNone(contact.deleted_at)


class CircularStakeholderTests(TestCase):
    """Auto-relations break circular references (two entities linked both ways)."""

    def test_mutually_linked_entities_are_deletable(self):
        p = _make_entity("Circular P")
        q = _make_entity("Circular Q")
        s1 = Stakeholder.objects.create(
            parent=p, target=q, role=StakeholderRole.VENDOR, active=True
        )
        s2 = Stakeholder.objects.create(
            parent=q, target=p, role=StakeholderRole.VENDOR, active=True
        )

        # Without the auto list this would deadlock: p is referenced by s1
        # (parent) and s2 (target). Both are auto soft-deleted, so p goes.
        p.delete()
        s1.refresh_from_db()
        s2.refresh_from_db()
        self.assertIsNotNone(s1.deleted_at)
        self.assertIsNotNone(s2.deleted_at)
        p.refresh_from_db()
        self.assertIsNotNone(p.deleted_at)

        # q no longer has live links, so it is deletable too.
        q.delete()
        q.refresh_from_db()
        self.assertIsNotNone(q.deleted_at)
