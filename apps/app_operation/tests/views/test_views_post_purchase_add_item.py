"""POST tests for the purchase wizard's add-item view.

Covers tag auto-suggestion for INDIVIDUAL templates: two pending lines of the
same template must never be assigned the same auto-generated tag before either
is persisted (the false "already used by another item" error).
"""

from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.models import Product, ProductTemplate
from apps.app_inventory.tests.general import make_user


class PurchaseAddItemTagTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_add_item", is_staff=True)
        self.client.login(username="officer_add_item", password="testpass")
        self.project = Entity.create(EntityType.PROJECT, name="Farm")
        self.template = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            tracking_mode=ProductTemplate.TrackingMode.INDIVIDUAL,
            default_unit="Head",
            tag_prefix="CALF",
            has_tag=True,
        )
        self.template.entities.add(self.project)
        self.url = reverse("purchase_add_item", kwargs={"pk": self.project.pk})
        self._start_session()

    def _start_session(self):
        session = self.client.session
        session[f"purchase_wizard_{self.project.pk}"] = {
            "total_amount": "100.00",
            "items": [],
        }
        session.save()

    def _add_item(self, unique_id=""):
        return self.client.post(
            self.url,
            {
                "product_template_id": self.template.pk,
                "description": "",
                "quantity": "1.00",
                "unit_price": "100.00",
                "unique_id": unique_id,
                "received_qty": "0",
            },
        )

    def _session_items(self):
        return self.client.session[f"purchase_wizard_{self.project.pk}"]["items"]

    def _add_form_suggestion(self):
        response = self.client.get(self.url, {"template_id": self.template.pk})
        return response.context["form"].initial.get("unique_id")

    def test_add_form_prefills_first_free_tag(self):
        self.assertEqual(self._add_form_suggestion(), "CALF1")

    def test_add_form_suggestion_accounts_for_pending_items(self):
        self._add_item("")
        self.assertEqual(self._add_form_suggestion(), "CALF2")

    def test_add_form_suggestion_accounts_for_existing_stock(self):
        Product.objects.create(
            entity=self.project,
            product_template=self.template,
            quantity=1,
            unit_price=Decimal("100.00"),
            unique_id="CALF7",
        )
        self.assertEqual(self._add_form_suggestion(), "CALF8")

    def test_blank_tag_on_second_line_gets_distinct_suggestion(self):
        self._add_item("")
        self._add_item("")
        tags = [it["unique_id"] for it in self._session_items()]
        self.assertEqual(tags, ["CALF1", "CALF2"])

    def test_explicit_duplicate_tag_is_still_rejected(self):
        self._add_item("CALF1")
        response = self._add_item("CALF1")
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertIn(
            "unique_id",
            form.errors,
        )
        self.assertEqual(len(self._session_items()), 1)

    def test_explicit_tag_reserves_it_for_next_blank_line(self):
        self._add_item("CALF2")
        self._add_item("")
        tags = [it["unique_id"] for it in self._session_items()]
        self.assertEqual(tags, ["CALF2", "CALF1"])
