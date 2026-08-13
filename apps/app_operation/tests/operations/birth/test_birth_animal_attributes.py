from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.forms import InvoiceItemCreateForm, InvoiceItemCreateFormSet
from apps.app_inventory.models import Product, ProductTemplate
from apps.app_inventory.tests.general import make_invoice_item, make_operation
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import BirthOperation, DeathOperation

User = get_user_model()


class BirthAnimalAttributesTest(TestCase):
    """A birth must record the newborn's gender, birth date and mother, and
    default the newborn template to the mother template's 'gives_birth_to'."""

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.officer_user = User.objects.create_user(
            username="officer", password="testpass", is_staff=True
        )
        self.project_entity = Entity.create(
            EntityType.PROJECT, name="Test Farm Project"
        )

        self.cow_template = ProductTemplate.objects.create(
            name="Dairy Cow",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            default_unit="Head",
            animal_type="Cow",
            gender=ProductTemplate.Gender.FEMALE,
        )
        self.calf_template = ProductTemplate.objects.create(
            name="Calf",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            default_unit="Head",
            animal_type="Calf",
            gender=ProductTemplate.Gender.MIXED,
        )
        self.cow_template.gives_birth_to = self.calf_template
        self.cow_template.save()
        self.cow_template.entities.add(self.project_entity)
        self.calf_template.entities.add(self.project_entity)

        self.mother = Product.objects.create(
            entity=self.project_entity,
            product_template=self.cow_template,
            quantity=1,
            unit_price=Decimal("1000.00"),
            unique_id="COW1",
            gender=Product.Gender.FEMALE,
            birth_date=date(2023, 1, 1),
        )

    def _birth(self, gender="FEMALE", qty=Decimal("1.00"), price=Decimal("100.00")):
        op_date = date.today()
        raw_post = {
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-id": "",
            "items-0-product_template": str(self.cow_template.pk),
            "items-0-quantity": str(qty),
            "items-0-unit_price": str(price),
            "items-0-description": "",
            "items-0-unique_id": "",
            "items-0-mother": str(self.mother.pk),
            "items-0-gender": gender,
            "items-0-birth_date": op_date.isoformat(),
            "items-0-DELETE": "",
        }
        return BirthOperation.create(
            operation_type=OperationType.BIRTH,
            source=self.system_entity,
            destination=self.project_entity,
            amount=(qty * price).quantize(Decimal("0.01")),
            date=op_date,
            description="Test birth",
            officer=self.officer_user,
            amount_paid=Decimal("0.00"),
            raw_post=raw_post,
            project=self.project_entity,
        )

    def test_birth_sets_gender_birth_date_and_mother(self):
        op = self._birth(gender="FEMALE")

        newborn = op.movement_lines.first().product
        self.assertIsNotNone(newborn)
        self.assertEqual(newborn.gender, Product.Gender.FEMALE)
        self.assertEqual(newborn.birth_date, date.today())
        self.assertEqual(newborn.mother, self.mother)

    def test_birth_defaults_newborn_template_to_gives_birth_to(self):
        op = self._birth(gender="MALE")

        newborn = op.movement_lines.first().product
        self.assertEqual(newborn.product_template, self.calf_template)

    def test_birth_male_gender_recorded(self):
        op = self._birth(gender="MALE")

        newborn = op.movement_lines.first().product
        self.assertEqual(newborn.gender, Product.Gender.MALE)

    # ------------------------------------------------------------------
    # VC17 — mother picker restricted to ACTIVE female/mixed animals
    # ------------------------------------------------------------------

    def _make_dead_female(self):
        """A female animal of the project that has died (status DEAD)."""
        dead = Product.objects.create(
            entity=self.project_entity,
            product_template=self.cow_template,
            quantity=1,
            unit_price=Decimal("1000.00"),
            unique_id="COW-DEAD",
            gender=Product.Gender.FEMALE,
        )
        dead_op = make_operation(
            self.project_entity,
            self.system_entity,
            self.officer_user,
            DeathOperation,
            OperationType.DEATH,
            amount=Decimal("1000.00"),
        )
        dead_item = make_invoice_item(
            dead_op, self.cow_template, Decimal("1"), Decimal("1000.00")
        )
        dead.invoice_items.add(dead_item)
        self.assertEqual(dead.status, Product.Status.DEAD)
        return dead

    def test_mother_picker_only_lists_active_female_mixed(self):
        """The mother dropdown must not offer SOLD/DEAD/CONSUMED/REMOVED animals."""
        dead = self._make_dead_female()

        form = InvoiceItemCreateForm(project=self.project_entity, is_birth=True)
        mother_ids = set(
            form.fields["mother"].queryset.values_list("pk", flat=True)
        )

        self.assertIn(self.mother.pk, mother_ids, "ACTIVE mother must be selectable")
        self.assertNotIn(
            dead.pk, mother_ids, "DEAD animal must not appear in the mother picker"
        )

    def test_mother_must_be_active_form_error(self):
        """A crafted POST referencing a non-active mother is rejected (VC17)."""
        dead = self._make_dead_female()

        raw_post = {
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-id": "",
            "items-0-product_template": str(self.calf_template.pk),
            "items-0-quantity": "1",
            "items-0-unit_price": "100",
            "items-0-description": "",
            "items-0-unique_id": "",
            "items-0-mother": str(dead.pk),
            "items-0-gender": "FEMALE",
            "items-0-birth_date": date.today().isoformat(),
            "items-0-DELETE": "",
        }
        formset = InvoiceItemCreateFormSet(
            data=raw_post,
            instance=BirthOperation(
                operation_type=OperationType.BIRTH,
                source=self.system_entity,
                destination=self.project_entity,
                amount=Decimal("100.00"),
                date=date.today(),
                description="Test birth",
                officer=self.officer_user,
            ),
            project=self.project_entity,
            is_birth=True,
        )

        # The restricted picker excludes the DEAD mother, so the standard
        # ModelChoiceField validation rejects the crafted choice (VC17).
        self.assertFalse(formset.is_valid())
        mother_errors = formset.forms[0].errors.get("mother", [])
        self.assertTrue(
            mother_errors, "A non-active mother must be rejected at form level"
        )

    def test_mother_active_passes_form_validation(self):
        """An ACTIVE mother still validates cleanly through the birth form."""
        raw_post = {
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-id": "",
            "items-0-product_template": str(self.cow_template.pk),
            "items-0-quantity": "1",
            "items-0-unit_price": "100",
            "items-0-description": "",
            "items-0-unique_id": "",
            "items-0-mother": str(self.mother.pk),
            "items-0-gender": "FEMALE",
            "items-0-birth_date": date.today().isoformat(),
            "items-0-DELETE": "",
        }
        formset = InvoiceItemCreateFormSet(
            data=raw_post,
            instance=BirthOperation(
                operation_type=OperationType.BIRTH,
                source=self.system_entity,
                destination=self.project_entity,
                amount=Decimal("100.00"),
                date=date.today(),
                description="Test birth",
                officer=self.officer_user,
            ),
            project=self.project_entity,
            is_birth=True,
        )

        self.assertTrue(formset.is_valid(), formset.errors)
