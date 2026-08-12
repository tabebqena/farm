from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import (
    InvoiceItem,
    Product,
    ProductTemplate,
)
from apps.app_inventory.tests.general import (
    make_entity,
    make_invoice_item,
    make_operation,
    make_product,
    make_product_template,
    make_user,
)
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import PurchaseOperation


class ProductTemplateAnimalAttributesTest(TestCase):
    def test_animal_defaults(self):
        t = make_product_template("Dairy Cow")
        self.assertEqual(t.animal_type, "")
        self.assertEqual(t.gender, ProductTemplate.Gender.NA)
        self.assertTrue(t.can_die)
        # clean() (run on every save via full_clean) forces animals to be
        # non-consumable.
        self.assertFalse(t.can_be_consumed)

    def test_animal_clean_forces_not_consumable(self):
        t = make_product_template("Bull")
        t.can_be_consumed = True
        t.full_clean()
        self.assertFalse(t.can_be_consumed)

    def test_non_animal_defaults_are_consumable_but_do_not_die(self):
        feed = ProductTemplate.objects.create(
            name="Starter Feed",
            nature=ProductTemplate.Nature.FEED,
            default_unit="Kg",
        )
        self.assertTrue(feed.can_be_consumed)
        self.assertFalse(feed.can_die)
        self.assertEqual(feed.gender, ProductTemplate.Gender.NA)

    def test_gives_birth_to_must_be_animal(self):
        cow = make_product_template("Dairy Cow")
        feed = ProductTemplate.objects.create(
            name="Feed", nature=ProductTemplate.Nature.FEED, default_unit="Kg"
        )
        cow.gender = ProductTemplate.Gender.FEMALE
        cow.gives_birth_to = feed
        with self.assertRaises(ValidationError):
            cow.full_clean()

    def test_gives_birth_to_requires_female_or_mixed(self):
        bull = make_product_template("Bull")
        calf = make_product_template("Calf")
        bull.gender = ProductTemplate.Gender.MALE
        bull.gives_birth_to = calf
        with self.assertRaises(ValidationError):
            bull.full_clean()

    def test_gives_birth_to_ok_for_female(self):
        cow = make_product_template("Dairy Cow")
        calf = make_product_template("Calf")
        cow.gender = ProductTemplate.Gender.FEMALE
        cow.gives_birth_to = calf
        cow.full_clean()  # must not raise

    def test_produces_must_be_feed_or_product(self):
        cow = make_product_template("Dairy Cow")
        calf = make_product_template("Calf")
        cow.produces.add(calf)  # ANIMAL template → invalid
        with self.assertRaises(ValidationError):
            cow.full_clean()

    def test_produces_ok_for_output_template(self):
        cow = make_product_template("Dairy Cow")
        milk = ProductTemplate.objects.create(
            name="Milk", nature=ProductTemplate.Nature.PRODUCT, default_unit="Litre"
        )
        cow.produces.add(milk)
        cow.full_clean()  # must not raise
        self.assertIn(milk, cow.produces.all())
        # Asymmetrical reverse relation
        self.assertIn(cow, milk.produced_by.all())


class AcceptsOperationGatingTest(TestCase):
    def test_animal_accepts_death_but_not_consumption(self):
        t = make_product_template()
        self.assertTrue(t.accepts_operation(OperationType.DEATH))
        self.assertFalse(t.accepts_operation(OperationType.CONSUMPTION))

    def test_feed_consumption_gated_by_flag(self):
        feed = ProductTemplate.objects.create(
            name="Feed", nature=ProductTemplate.Nature.FEED, default_unit="Kg"
        )
        self.assertTrue(feed.accepts_operation(OperationType.CONSUMPTION))
        feed.can_be_consumed = False
        feed.save()
        self.assertFalse(feed.accepts_operation(OperationType.CONSUMPTION))

    def test_death_gated_by_can_die(self):
        animal = make_product_template()
        animal.can_die = False
        animal.save()
        self.assertFalse(animal.accepts_operation(OperationType.DEATH))
        self.assertFalse(animal.accepts_operation(OperationType.CONSUMPTION))


class ProductAnimalAttributesTest(TestCase):
    def _make_vendor(self, project):
        vendor = make_entity(EntityType.PERSON, "Vendor", is_vendor=True)
        Stakeholder.objects.create(
            parent=project,
            target=vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        return vendor

    def test_create_products_for_item_sets_gender_and_birth(self):
        entity = make_entity(EntityType.PROJECT)
        vendor = self._make_vendor(entity)
        template = make_product_template("Dairy Cow")
        template.gender = ProductTemplate.Gender.FEMALE
        template.save()
        op = make_operation(
            entity,
            vendor,
            make_user(),
            PurchaseOperation,
            OperationType.PURCHASE,
            amount=Decimal("100.00"),
        )
        item = make_invoice_item(op, template, Decimal("1.00"), Decimal("100.00"))
        products = InvoiceItem.create_products_for_item(
            invoice_item=item,
            entity=entity,
            quantity=Decimal("1.00"),
            unit_price=Decimal("100.00"),
            birth_date=date(2026, 1, 15),
        )
        self.assertEqual(products[0].gender, Product.Gender.FEMALE)
        self.assertEqual(products[0].birth_date, date(2026, 1, 15))

    def test_explicit_gender_overrides_template(self):
        entity = make_entity(EntityType.PROJECT)
        vendor = self._make_vendor(entity)
        template = make_product_template("Calf")
        template.gender = ProductTemplate.Gender.FEMALE
        template.save()
        op = make_operation(
            entity,
            vendor,
            make_user(),
            PurchaseOperation,
            OperationType.PURCHASE,
            amount=Decimal("100.00"),
        )
        item = make_invoice_item(op, template, Decimal("1.00"), Decimal("100.00"))
        products = InvoiceItem.create_products_for_item(
            invoice_item=item,
            entity=entity,
            quantity=Decimal("1.00"),
            unit_price=Decimal("100.00"),
            gender=Product.Gender.MALE,
        )
        self.assertEqual(products[0].gender, Product.Gender.MALE)


