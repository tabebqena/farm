from datetime import date
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import InventoryMovement, InventoryMovementLine
from apps.app_inventory.tests.general import (
    make_entity,
    make_invoice_item,
    make_operation,
    make_product_template,
    make_project_entity,
    make_user,
)
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import PurchaseOperation, SaleOperation


class InventoryMovementCreationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer1", is_staff=True)
        self.non_officer = make_user(username="non_officer", is_staff=False)
        self.system = Entity.create(EntityType.SYSTEM)
        self.vendor = make_entity(EntityType.PERSON, "Vendor", is_vendor=True)
        self.project = make_project_entity("Farm")
        Stakeholder.objects.create(
            parent=self.project,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        self.client_entity = make_entity(EntityType.PERSON, "Client", is_client=True)
        Stakeholder.objects.create(
            parent=self.project,
            target=self.client_entity,
            active=True,
            role=StakeholderRole.CLIENT,
        )
        self.template = make_product_template("Calves")

    def test_create_inventory_movement_purchase(self):
        """Test creating an inventory movement for a PURCHASE operation."""
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
        )
        item = make_invoice_item(purchase, self.template, quantity=Decimal("5.00"))

        self.client.login(username="officer1", password="testpass")
        url = reverse("create_inventory_movement", kwargs={"operation_pk": purchase.pk})
        response = self.client.post(
            url,
            {
                "date": date.today().isoformat(),
                "notes": "Test movement",
                "lines-TOTAL_FORMS": "2",
                "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
                "lines-0-invoice_item": item.pk,
                "lines-0-quantity": "3.00",
                "lines-1-invoice_item": "",
                "lines-1-quantity": "",
            },
        )

        # Should redirect to operation detail on success
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            InventoryMovement.objects.filter(operation=purchase).exists(),
            "InventoryMovement should be created",
        )
        movement = InventoryMovement.objects.get(operation=purchase)
        self.assertEqual(movement.date, date.today())
        self.assertEqual(movement.notes, "Test movement")
        self.assertEqual(movement.officer, self.officer)

        # Check that the line was created
        self.assertEqual(movement.lines.count(), 1)
        line = movement.lines.first()
        self.assertEqual(line.invoice_item, item)
        self.assertEqual(line.quantity, Decimal("3.00"))

    def test_non_staff_cannot_create_movement(self):
        """Test that non-staff users cannot create movements."""
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
        )

        self.client.login(username="non_officer", password="testpass")
        url = reverse("create_inventory_movement", kwargs={"operation_pk": purchase.pk})
        response = self.client.post(url)

        # Should redirect to entity_list
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            InventoryMovement.objects.filter(operation=purchase).exists(),
            "Non-staff should not be able to create movements",
        )

    def test_sale_operation_movement(self):
        """Test creating a movement for a SALE operation."""
        sale = make_operation(
            source=self.client_entity,
            destination=self.project,
            officer=self.officer,
            proxy_class=SaleOperation,
            operation_type=OperationType.SALE,
        )
        item = make_invoice_item(sale, self.template, quantity=Decimal("10.00"))

        self.client.login(username="officer1", password="testpass")
        url = reverse("create_inventory_movement", kwargs={"operation_pk": sale.pk})
        response = self.client.post(
            url,
            {
                "date": date.today().isoformat(),
                "notes": "Sale shipment",
                "lines-TOTAL_FORMS": "1",
                "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
                "lines-0-invoice_item": item.pk,
                "lines-0-quantity": "8.00",
            },
        )

        self.assertEqual(response.status_code, 302)
        movement = InventoryMovement.objects.get(operation=sale)
        self.assertEqual(movement.lines.count(), 1)
        self.assertEqual(movement.lines.first().quantity, Decimal("8.00"))

    def test_quantity_exceeds_invoice_item(self):
        """Test that validation fails when movement qty exceeds invoice qty."""
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
        )
        item = make_invoice_item(purchase, self.template, quantity=Decimal("5.00"))

        self.client.login(username="officer1", password="testpass")
        url = reverse("create_inventory_movement", kwargs={"operation_pk": purchase.pk})
        response = self.client.post(
            url,
            {
                "date": date.today().isoformat(),
                "notes": "",
                "lines-TOTAL_FORMS": "1",
                "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
                "lines-0-invoice_item": item.pk,
                "lines-0-quantity": "10.00",  # Exceeds invoice qty of 5
            },
        )

        # Should not create movement
        self.assertFalse(
            InventoryMovement.objects.filter(operation=purchase).exists(),
            "Movement should not be created when qty exceeds invoice",
        )

    def test_get_request_shows_form(self):
        """Test that GET request shows the form with empty formset."""
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
        )

        self.client.login(username="officer1", password="testpass")
        url = reverse("create_inventory_movement", kwargs={"operation_pk": purchase.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("formset", response.context)
        self.assertIn("operation", response.context)
