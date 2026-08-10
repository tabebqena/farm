from decimal import Decimal

from django.test import TestCase

from apps.app_entity.models import EntityType
from apps.app_inventory.tests.general import make_entity, make_product_template
from apps.app_inventory.models import Product, ProductTemplate


class ProductTemplateTest(TestCase):
    def test_str_returns_name(self):
        t = make_product_template("Fattening Calves")
        self.assertEqual(str(t), "Fattening Calves")

    def test_default_nature_is_animal(self):
        t = make_product_template()
        self.assertEqual(t.nature, ProductTemplate.Nature.ANIMAL)

    def test_animal_tracking_mode_is_individual(self):
        """ANIMAL templates are always INDIVIDUAL (never BATCH)."""
        t = make_product_template()
        self.assertEqual(t.tracking_mode, ProductTemplate.TrackingMode.INDIVIDUAL)

    def test_default_unit(self):
        t = make_product_template()
        self.assertEqual(t.default_unit, "Head")

    def test_has_tag_defaults_false(self):
        t = make_product_template()
        self.assertFalse(t.has_tag)

    def test_minimum_quantity_default(self):
        t = make_product_template()
        self.assertEqual(t.minimum_quantity, Decimal("1.00"))

    def test_entities_m2m(self):
        t = make_product_template()
        e = make_entity(EntityType.PROJECT)
        t.entities.add(e)
        self.assertIn(e, t.entities.all())

    def test_name_ar_defaults_blank(self):
        t = make_product_template()
        self.assertEqual(t.name_ar, "")

    def test_name_ar_can_be_set(self):
        t = make_product_template()
        t.name_ar = "عجول تسمين"
        t.save()
        t.refresh_from_db()
        self.assertEqual(t.name_ar, "عجول تسمين")

    # ------------------------------------------------------------------
    # Nature → tracking mode enforcement
    # ------------------------------------------------------------------

    def test_tracking_mode_forced_by_nature(self):
        """clean()/save() forces INDIVIDUAL for ANIMAL, COMMODITY otherwise."""
        animal = ProductTemplate.objects.create(
            name="Animal X",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            default_unit="Head",
        )
        self.assertEqual(
            animal.tracking_mode, ProductTemplate.TrackingMode.INDIVIDUAL
        )

        feed = ProductTemplate.objects.create(
            name="Feed X",
            nature=ProductTemplate.Nature.FEED,
            default_unit="Kg",
        )
        self.assertEqual(feed.tracking_mode, ProductTemplate.TrackingMode.COMMODITY)

    def test_tracking_mode_for_nature_classmethod(self):
        self.assertEqual(
            ProductTemplate.tracking_mode_for_nature(ProductTemplate.Nature.ANIMAL),
            ProductTemplate.TrackingMode.INDIVIDUAL,
        )
        self.assertEqual(
            ProductTemplate.tracking_mode_for_nature(ProductTemplate.Nature.FEED),
            ProductTemplate.TrackingMode.COMMODITY,
        )
        self.assertEqual(
            ProductTemplate.tracking_mode_for_nature(ProductTemplate.Nature.MEDICINE),
            ProductTemplate.TrackingMode.COMMODITY,
        )
        self.assertEqual(
            ProductTemplate.tracking_mode_for_nature(ProductTemplate.Nature.PRODUCT),
            ProductTemplate.TrackingMode.COMMODITY,
        )

    def test_tracking_mode_choices_have_no_batch(self):
        values = [v for v, _ in ProductTemplate.TrackingMode.choices]
        self.assertNotIn("BATCH", values)
        self.assertIn("INDIVIDUAL", values)
        self.assertIn("COMMODITY", values)

    # ------------------------------------------------------------------
    # Tag auto-generation
    # ------------------------------------------------------------------

    def test_effective_tag_prefix_uses_explicit(self):
        t = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            default_unit="Head",
            tag_prefix="CALF",
        )
        self.assertEqual(t.effective_tag_prefix, "CALF")

    def test_effective_tag_prefix_derives_from_name(self):
        t = ProductTemplate.objects.create(
            name="Fattening Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            default_unit="Head",
        )
        self.assertEqual(t.effective_tag_prefix, "FATT")

    def test_next_tag_sequence(self):
        entity = make_entity(EntityType.PROJECT)
        t = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            default_unit="Head",
            tag_prefix="CALF",
        )
        # No products yet → starts at 1
        self.assertEqual(t.next_tag(entity), "CALF1")

        # Creating products advances the sequence
        for i in range(3):
            Product.objects.create(
                entity=entity,
                product_template=t,
                quantity=1,
                unit_price=Decimal("100.00"),
                unique_id=t.next_tag(entity),
            )
        self.assertEqual(t.next_tag(entity), "CALF4")

    def test_next_tag_skips_edited_high_suffixes(self):
        entity = make_entity(EntityType.PROJECT)
        t = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            default_unit="Head",
            tag_prefix="CALF",
        )
        # A user-edited tag with a high number bumps the next suggestion
        Product.objects.create(
            entity=entity,
            product_template=t,
            quantity=1,
            unit_price=Decimal("100.00"),
            unique_id="CALF42",
        )
        self.assertEqual(t.next_tag(entity), "CALF43")

    def test_next_tag_ignores_other_prefixes(self):
        entity = make_entity(EntityType.PROJECT)
        t = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            default_unit="Head",
            tag_prefix="CALF",
        )
        Product.objects.create(
            entity=entity,
            product_template=t,
            quantity=1,
            unit_price=Decimal("100.00"),
            unique_id="OTHER5",
        )
        self.assertEqual(t.next_tag(entity), "CALF1")

    def test_next_tag_unique_per_entity(self):
        e1 = make_entity(EntityType.PROJECT, "Farm A")
        e2 = make_entity(EntityType.PROJECT, "Farm B")
        t = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            default_unit="Head",
            tag_prefix="CALF",
        )
        Product.objects.create(
            entity=e1,
            product_template=t,
            quantity=1,
            unit_price=Decimal("100.00"),
            unique_id="CALF1",
        )
        # Each entity has its own numbering
        self.assertEqual(t.next_tag(e1), "CALF2")
        self.assertEqual(t.next_tag(e2), "CALF1")
