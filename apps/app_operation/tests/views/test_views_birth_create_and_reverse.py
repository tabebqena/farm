"""View-level contract for the Birth operation (§8 of op_17_birth.md).

Covers:
- GET  /<project_pk>/birth/create renders the dedicated birth form with the
  source locked to the System entity and no secondary-entity picker.
- POST /<project_pk>/birth/create drives the full OperationDataValidator +
  InvoiceItemCreateFormSet + BirthOperation.create() pipeline.
- POST /<pk>/reverse/ without a reason is rejected (VR5); with a reason the
  birth is reversed and the reason flows to the reversal description.
"""
from datetime import date
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.models import Product, ProductTemplate
from apps.app_inventory.tests.general import make_user
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import BirthOperation


class BirthCreateViewTest(TestCase):
    """§8 — the dedicated BirthCreateView at /<pk>/birth/create."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_birth", is_staff=True)
        self.client.login(username="officer_birth", password="testpass")
        self.system = Entity.create(EntityType.SYSTEM)
        self.project = Entity.create(EntityType.PROJECT, name="Birth Project")
        self.template = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            tracking_mode=ProductTemplate.TrackingMode.INDIVIDUAL,
            default_unit="Head",
        )
        self.template.entities.add(self.project)

    def test_get_birth_create_renders_birth_form(self):
        """The birth create page renders and locks the source to the System."""
        response = self.client.get(
            reverse("birth_create_view", kwargs={"pk": self.project.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["source_entity"], self.system)
        self.assertEqual(response.context["config"]["source"], "system")
        self.assertEqual(response.context["config"]["dest"], "url")
        # No secondary-entity picker for a URL-destination operation.
        self.assertEqual(response.context["entities"], [])
        self.assertIsNone(response.context["secondary_entity"])
        self.assertIsNotNone(response.context["formset"])
        self.assertFalse(response.context["can_pay"])
        self.assertIn("birth_form", response.templates[0].name or "")

    def test_post_birth_create_creates_operation_with_movements(self):
        """POST drives the full create pipeline: op + auto inbound lines."""
        raw_post = {
            "date": date.today().isoformat(),
            "description": "Birth via view",
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-id": "",
            "items-0-product_template": str(self.template.pk),
            "items-0-quantity": "2",
            "items-0-unit_price": "100.00",
            "items-0-description": "",
            "items-0-unique_id": "",
            "items-0-DELETE": "",
        }
        response = self.client.post(
            reverse("birth_create_view", kwargs={"pk": self.project.pk}),
            raw_post,
        )

        self.assertEqual(response.status_code, 302)
        op = BirthOperation.objects.get(
            destination=self.project, operation_type=OperationType.BIRTH
        )
        self.assertEqual(op.movement_lines.count(), 2)
        for ml in op.movement_lines.all():
            self.assertEqual(ml.product.status, Product.Status.ACTIVE)
        self.assertEqual(op.get_all_transactions().count(), 0)


class BirthReverseViewTest(TestCase):
    """§8 / §5.2.1 VR5 — the reverse view requires a reversal reason."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_birth_rev", is_staff=True)
        self.client.login(username="officer_birth_rev", password="testpass")
        self.system = Entity.create(EntityType.SYSTEM)
        self.project = Entity.create(EntityType.PROJECT, name="Birth Project")
        self.template = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            tracking_mode=ProductTemplate.TrackingMode.INDIVIDUAL,
            default_unit="Head",
        )
        self.template.entities.add(self.project)

    def _make_birth(self):
        raw_post = {
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-id": "",
            "items-0-product_template": str(self.template.pk),
            "items-0-quantity": "1",
            "items-0-unit_price": "100.00",
            "items-0-description": "",
            "items-0-unique_id": "",
            "items-0-DELETE": "",
        }
        return BirthOperation.create(
            operation_type=OperationType.BIRTH,
            source=self.system,
            destination=self.project,
            amount=Decimal("100.00"),
            date=date.today(),
            description="Test birth",
            officer=self.officer,
            amount_paid=Decimal("0.00"),
            raw_post=raw_post,
            project=self.project,
        )

    def test_reverse_view_rejects_missing_reason(self):
        """VR5 — POST without a reason does not reverse the birth."""
        op = self._make_birth()
        url = reverse("operation_reverse_view", kwargs={"pk": op.pk})

        response = self.client.post(url, {"reversal_reason": "   "})

        self.assertEqual(response.status_code, 200)
        op.refresh_from_db()
        self.assertFalse(op.is_reversed, "Missing reason must not reverse the birth")

    def test_reverse_view_with_reason_reverses_and_flows_reason(self):
        """VR5 + SR10 — with a reason the birth is reversed and the reason is
        stored on the reversal record."""
        op = self._make_birth()
        url = reverse("operation_reverse_view", kwargs={"pk": op.pk})

        response = self.client.post(url, {"reversal_reason": "wrong entry"})

        self.assertEqual(response.status_code, 302)
        op.refresh_from_db()
        self.assertTrue(op.is_reversed)
        self.assertEqual(op.reversed_by.description, "wrong entry")
