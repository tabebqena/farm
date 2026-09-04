"""Tests for ``manage.py seed`` and the animal ``ProductTemplate`` catalog it
creates from ``ANIMAL_TEMPLATES``.
"""

from django.core.management import call_command
from django.test import TestCase

from apps.app_base.management.commands.seed import ANIMAL_TEMPLATES
from apps.app_inventory.models import ProductTemplate


class SeedCommandProductTemplatesTest(TestCase):
    """The seed command must create the species × stage × gender animal
    templates (Cow / Buffalo / Sheep / Goat) with the new animal attributes,
    prune the removed templates, and be idempotent."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed")

    @staticmethod
    def _name(entry):
        return f"{entry['animal_type']} {entry['stage']} {entry['gender'].title()}"

    def test_all_animal_templates_created_with_attributes(self):
        for entry in ANIMAL_TEMPLATES:
            with self.subTest(entry=self._name(entry)):
                t = ProductTemplate.objects.get(name=self._name(entry))
                self.assertEqual(t.nature, ProductTemplate.Nature.ANIMAL)
                self.assertEqual(t.animal_type, entry["animal_type"])
                self.assertEqual(t.gender, entry["gender"])
                self.assertEqual(t.tag_prefix, entry["tag_prefix"])
                self.assertTrue(t.has_tag)
                self.assertTrue(t.can_die)
                self.assertFalse(t.can_be_consumed)
                self.assertEqual(
                    set(t.produces.values_list("name", flat=True)),
                    set(entry["produces"]),
                )

    def test_only_four_species_are_seeded(self):
        """No ANIMAL template exists outside Cow/Buffalo/Sheep/Goat."""
        self.assertEqual(
            ProductTemplate.objects.filter(nature=ProductTemplate.Nature.ANIMAL).count(),
            len(ANIMAL_TEMPLATES),
        )

    def test_gives_birth_to_resolution(self):
        expected = {
            "Cow Adult Female": "Cow Calf Female",
            "Buffalo Adult Female": "Buffalo Calf Female",
            "Sheep Adult Female": "Sheep Calf Female",
            "Goat Adult Female": "Goat Calf Female",
        }
        for source, target in expected.items():
            with self.subTest(source=source):
                self.assertEqual(
                    ProductTemplate.objects.get(name=source).gives_birth_to.name,
                    target,
                )
        # Male and calf templates never give birth.
        for name in (
            "Cow Adult Male",
            "Cow Calf Male",
            "Cow Calf Female",
            "Buffalo Adult Male",
            "Buffalo Calf Male",
            "Sheep Calf Female",
            "Goat Adult Male",
            "Goat Calf Female",
        ):
            with self.subTest(name=name):
                self.assertIsNone(ProductTemplate.objects.get(name=name).gives_birth_to)

    def test_removed_templates_are_not_created(self):
        removed = [
            "Fattening Cattle",
            "Dairy Cows",
            "Breeding Bulls",
            "Replacement Heifers",
            "Calves",
            "Fattening Lambs",
            "Breeding Ewes",
            "Breeding Rams",
            "Fattening Kids",
            "Breeding Does",
            "Breeding Bucks",
            "Fattening Camels (Hashi)",
            "Horses",
            "Donkeys / Mules",
            "Broiler Chickens",
            "Laying Hens",
            "Fattening Turkeys",
            "Fattening Ducks / Geese",
            "Fattening Rabbits",
            "Breeding Rabbits",
        ]
        for name in removed:
            with self.subTest(name=name):
                self.assertFalse(
                    ProductTemplate.objects.filter(name=name).exists(),
                    f"{name!r} should not be seeded",
                )

    def test_non_animal_templates_have_no_animal_flags(self):
        for t in ProductTemplate.objects.exclude(nature=ProductTemplate.Nature.ANIMAL):
            self.assertFalse(t.can_die)
            self.assertTrue(t.can_be_consumed)
            self.assertEqual(t.gender, ProductTemplate.Gender.NA)

    def test_seed_is_idempotent(self):
        before = ProductTemplate.objects.count()
        call_command("seed")  # must not raise
        self.assertEqual(ProductTemplate.objects.count(), before)
