"""View-level contract for the Death operation (§8 of op_18_death.md).

Covers:
- GET  /<project_pk>/death/create renders the dedicated death form with the
  source locked to the URL Project and the destination locked to the System,
  and no secondary-entity picker.
- POST /<project_pk>/death/create drives the full OperationDataValidator +
  InvoiceItemSelectFormSet + DeathOperation.create() pipeline (auto outbound
  movement line, status DEAD, no transactions).
- POST /<pk>/reverse/ without a reason is rejected (VR6); with a reason the
  death is reversed and the reason flows to the reversal description.
"""
from datetime import date
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import InventoryMovementLine, Product, ProductTemplate
from apps.app_inventory.tests.general import (
    make_entity,
    make_invoice_item,
    make_operation,
    make_user,
)
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import DeathOperation, PurchaseOperation


class DeathCreateViewTest(TestCase):
    """§8 — the dedicated DeathCreateView at /<pk>/death/create."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_death", is_staff=True)
        self.client.login(username="officer_death", password="testpass")
        self.system = Entity.create(EntityType.SYSTEM)
        self.project = Entity.create(EntityType.PROJECT, name="Death Project")
        self.vendor = make_entity(EntityType.PERSON, "Vendor", is_vendor=True)
        Stakeholder.objects.create(
            parent=self.project,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        self.template = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            default_unit="Head",
        )

    def _make_moved_product(self, qty=Decimal("5.00"), price=Decimal("100.00")):
        """Return an ACTIVE, physically-moved animal owned by the project."""
        purchase = make_operation(
            self.project,
            self.vendor,
            self.officer,
            PurchaseOperation,
            OperationType.PURCHASE,
            amount=(qty * price).quantize(Decimal("0.01")),
        )
        item = make_invoice_item(purchase, self.template, qty, price)
        product = Product.objects.create(
            product_template=self.template,
            entity=self.project,
            unit_price=price,
            quantity=int(qty),
        )
        product.invoice_items.add(item)
        InventoryMovementLine.objects.create(
            operation=purchase,
            invoice_item=item,
            product=product,
            quantity=qty,
            date=date.today(),
            officer=self.officer,
        )
        return product

    def test_get_death_create_renders_death_form(self):
        """The death create page renders and locks source/destination roles."""
        response = self.client.get(
            reverse("death_create_view", kwargs={"pk": self.project.pk})
        )

        self.assertEqual(response.status_code, 200)
        # Source role = url → the Project from the URL; no picker for either role.
        self.assertEqual(response.context["source_entity"], self.project)
        self.assertEqual(response.context["config"]["source"], "url")
        self.assertEqual(response.context["config"]["dest"], "system")
        self.assertEqual(response.context["entities"], [])
        self.assertIsNone(response.context["secondary_entity"])
        self.assertIsNotNone(response.context["formset"])
        self.assertFalse(response.context["can_pay"])
        self.assertIn("death_form", response.templates[0].name or "")

    def test_post_death_create_creates_death_with_movement(self):
        """POST drives the full pipeline: op + auto outbound movement + DEAD."""
        product = self._make_moved_product()
        raw_post = {
            "date": date.today().isoformat(),
            "description": "Death via view",
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-id": "",
            "items-0-quantity": "5",
            "items-0-unit_price": "100.00",
            "items-0-description": "",
            "items-0-selected_product": str(product.pk),
            "items-0-DELETE": "",
        }
        response = self.client.post(
            reverse("death_create_view", kwargs={"pk": self.project.pk}),
            raw_post,
        )

        self.assertEqual(response.status_code, 302)
        op = DeathOperation.objects.get(
            source=self.project, operation_type=OperationType.DEATH
        )
        self.assertEqual(op.movement_lines.count(), 1)
        self.assertEqual(op.movement_lines.first().product, product)
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.DEAD)
        self.assertEqual(op.get_all_transactions().count(), 0)


class DeathReverseViewTest(TestCase):
    """§8 / §5.2.1 VR6 — the reverse view requires a reversal reason."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_death_rev", is_staff=True)
        self.client.login(username="officer_death_rev", password="testpass")
        self.system = Entity.create(EntityType.SYSTEM)
        self.project = Entity.create(EntityType.PROJECT, name="Death Project")
        self.vendor = make_entity(EntityType.PERSON, "Vendor", is_vendor=True)
        Stakeholder.objects.create(
            parent=self.project,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        self.template = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            default_unit="Head",
        )

    def _make_dead(self):
        """Create a physically-moved ACTIVE animal and record its death."""
        purchase = make_operation(
            self.project,
            self.vendor,
            self.officer,
            PurchaseOperation,
            OperationType.PURCHASE,
            amount=Decimal("500.00"),
        )
        item = make_invoice_item(purchase, self.template, Decimal("5"), Decimal("100.00"))
        product = Product.objects.create(
            product_template=self.template,
            entity=self.project,
            unit_price=Decimal("100.00"),
            quantity=5,
        )
        product.invoice_items.add(item)
        InventoryMovementLine.objects.create(
            operation=purchase,
            invoice_item=item,
            product=product,
            quantity=Decimal("5.00"),
            date=date.today(),
            officer=self.officer,
        )

        raw_post = {
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-id": "",
            "items-0-quantity": "5.00",
            "items-0-unit_price": "100.00",
            "items-0-description": "",
            "items-0-selected_product": str(product.pk),
            "items-0-DELETE": "",
        }
        return DeathOperation.create(
            operation_type=OperationType.DEATH,
            source=self.project,
            destination=self.system,
            amount=Decimal("500.00"),
            date=date.today(),
            description="Test death",
            officer=self.officer,
            amount_paid=Decimal("0.00"),
            raw_post=raw_post,
            project=self.project,
        )

    def test_reverse_view_rejects_missing_reason(self):
        """VR6 — POST without a reason does not reverse the death."""
        op = self._make_dead()
        url = reverse("operation_reverse_view", kwargs={"pk": op.pk})

        response = self.client.post(url, {"reversal_reason": "   "})

        self.assertEqual(response.status_code, 200)
        op.refresh_from_db()
        self.assertFalse(op.is_reversed, "Missing reason must not reverse the death")

    def test_reverse_view_with_reason_reverses_and_flows_reason(self):
        """VR6 + SR — with a reason the death is reversed and the reason is
        stored on the reversal record."""
        op = self._make_dead()
        url = reverse("operation_reverse_view", kwargs={"pk": op.pk})

        response = self.client.post(url, {"reversal_reason": "wrong entry"})

        self.assertEqual(response.status_code, 302)
        op.refresh_from_db()
        self.assertTrue(op.is_reversed)
        self.assertEqual(op.reversed_by.description, "wrong entry")
