"""Tests for the purchase wizard's add-item view.

The Tag / ID is user-controlled: the field is never auto-filled (a blank value
is stored as-is, and the backend numbers the heads when products are created);
the view only shows the next available tag as a read-only hint.
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

    def _get_form(self):
        return self.client.get(self.url, {"template_id": self.template.pk})

    def test_field_is_left_empty_with_hint(self):
        response = self._get_form()
        self.assertEqual(response.context["form"].initial.get("unique_id"), None)
        self.assertEqual(response.context["suggested_tag"], "CALF1")

    def test_hint_accounts_for_explicit_pending_tags(self):
        self._add_item("CALF1")
        self.assertEqual(self._get_form().context["suggested_tag"], "CALF2")

    def test_hint_accounts_for_existing_stock(self):
        Product.objects.create(
            entity=self.project,
            product_template=self.template,
            quantity=1,
            unit_price=Decimal("100.00"),
            unique_id="CALF7",
        )
        self.assertEqual(self._get_form().context["suggested_tag"], "CALF8")

    def test_blank_tag_is_stored_blank_for_backend_to_number(self):
        self._add_item("")
        self._add_item("")
        tags = [it["unique_id"] for it in self._session_items()]
        self.assertEqual(tags, ["", ""])

    def test_explicit_tag_is_stored_as_typed(self):
        self._add_item("CALF42")
        self.assertEqual(self._session_items()[0]["unique_id"], "CALF42")

    def test_explicit_duplicate_tag_is_still_rejected(self):
        self._add_item("CALF1")
        response = self._add_item("CALF1")
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertIn("unique_id", form.errors)
        self.assertEqual(len(self._session_items()), 1)
