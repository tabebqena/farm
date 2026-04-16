from django.test import TestCase

from apps.app_entity.models import EntityType
from apps.app_inventory.tests.general import make_entity, make_product_template
from apps.app_inventory.models import ProductTemplate


class ProductTemplateTest(TestCase):
    def test_str_returns_name(self):
        t = make_product_template("Fattening Calves")
        self.assertEqual(str(t), "Fattening Calves")

    def test_default_nature_is_animal(self):
        t = make_product_template()
        self.assertEqual(t.nature, ProductTemplate.Nature.ANIMAL)

    def test_default_tracking_mode_is_batch(self):
        t = make_product_template()
        self.assertEqual(t.tracking_mode, ProductTemplate.TrackingMode.BATCH)

    def test_default_unit(self):
        t = make_product_template()
        self.assertEqual(t.default_unit, "Head")

    def test_requires_individual_tag_defaults_false(self):
        t = make_product_template()
        self.assertFalse(t.requires_individual_tag)

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
