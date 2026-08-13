"""View tests for the inventory movement actions registered in
docs/specs/features/stock.md §5.5 (reverse) / §5.2 (dispatch) / §8 (view & UI
contract): single reverse (MR1/MR2), batch reverse by group key (MS4), deferred
registration (INDIVIDUAL vs COMMODITY) and the backward-compatible movement
route.  These branches were previously unpinned by any view test.
"""

from datetime import date
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import InventoryMovementLine, Product, ProductTemplate
from apps.app_inventory.stock import movement_state
from apps.app_inventory.tests.general import (
    make_entity,
    make_invoice_item,
    make_operation,
    make_product,
    make_project_entity,
    make_user,
)
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import PurchaseOperation, SaleOperation


class MovementActionViewsTest(TestCase):
    """Reverse / batch-reverse / deferred / backward-compatible movement views."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_actions", is_staff=True)
        self.non_officer = make_user(username="clerk_actions", is_staff=False)
        self.system = Entity.create(EntityType.SYSTEM)
        self.vendor = make_entity(EntityType.PERSON, "Vendor", is_vendor=True)
        self.project = make_project_entity("Farm")
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
            tracking_mode=ProductTemplate.TrackingMode.INDIVIDUAL,
            default_unit="Head",
        )
        self.template.entities.add(self.project)

    def _make_received_line(self, qty=Decimal("5.00")):
        """A physically-present product owned by the project, with one inbound
        PURCHASE movement line."""
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
            amount=(qty * Decimal("100.00")).quantize(Decimal("0.01")),
        )
        item = make_invoice_item(
            purchase, self.template, quantity=qty, unit_price=Decimal("100.00")
        )
        product = Product.objects.create(
            product_template=self.template,
            entity=self.project,
            unit_price=Decimal("100.00"),
            quantity=int(qty),
        )
        product.invoice_items.add(item)
        return InventoryMovementLine.objects.create(
            operation=purchase,
            invoice_item=item,
            product=product,
            quantity=qty,
            date=date.today(),
            officer=self.officer,
        )

    # --- single reverse view (MR1 / MR2) -----------------------------------

    def test_reverse_movement_line_success(self):
        """A staff POST to the single-reverse view creates a reversal line and
        nets the product's stock back to zero (MS1/MS2)."""
        line = self._make_received_line()
        self.client.login(username="officer_actions", password="testpass")
        url = reverse("reverse_inventory_movement_line", kwargs={"pk": line.pk})

        response = self.client.post(url)

        self.assertRedirects(
            response,
            reverse("operation_detail_view", kwargs={"pk": line.operation_id}),
        )
        self.assertTrue(
            InventoryMovementLine.objects.filter(reversal_of=line).exists()
        )
        state = movement_state(line.product, as_of=date.today())
        self.assertEqual(state["quantity"], Decimal("0.00"))

    def test_reverse_movement_line_already_reversed_warns(self):
        """MR1 — reversing a line that already has a reversal is refused (the
        view warns and no second reversal is created)."""
        line = self._make_received_line()
        line.reverse(officer=self.officer)
        self.client.login(username="officer_actions", password="testpass")
        url = reverse("reverse_inventory_movement_line", kwargs={"pk": line.pk})

        response = self.client.post(url)

        self.assertRedirects(
            response,
            reverse("operation_detail_view", kwargs={"pk": line.operation_id}),
        )
        self.assertEqual(
            InventoryMovementLine.objects.filter(reversal_of=line).count(), 1
        )

    def test_reverse_movement_line_requires_officer(self):
        """MR2 — a non-staff user is redirected and no reversal is created."""
        line = self._make_received_line()
        self.client.login(username="clerk_actions", password="testpass")
        url = reverse("reverse_inventory_movement_line", kwargs={"pk": line.pk})

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            InventoryMovementLine.objects.filter(reversal_of=line).exists()
        )

    # --- batch reverse view (MS4) ------------------------------------------

    def _make_grouped_lines(self, group_key="grp123456", count=3):
        """*count* inbound lines sharing *group_key*."""
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
            amount=Decimal("300.00"),
        )
        item = make_invoice_item(
            purchase, self.template, quantity=Decimal("3.00")
        )
        product = make_product(self.template, entity=self.project, quantity=3)
        item.products.add(product)
        for _ in range(count):
            InventoryMovementLine.objects.create(
                operation=purchase,
                invoice_item=item,
                product=product,
                quantity=Decimal("1.00"),
                date=date.today(),
                officer=self.officer,
                group_key=group_key,
            )
        return purchase

    def test_batch_reverse_success(self):
        """MS4 — a staff POST reverses every line sharing the group key."""
        purchase = self._make_grouped_lines()
        self.client.login(username="officer_actions", password="testpass")
        url = reverse(
            "batch_reverse_inventory_movement_lines", kwargs={"group_key": "grp123456"}
        )

        response = self.client.post(url)

        self.assertRedirects(
            response,
            reverse("operation_detail_view", kwargs={"pk": purchase.pk}),
        )
        originals = InventoryMovementLine.objects.filter(
            group_key="grp123456", reversal_of__isnull=True
        )
        self.assertEqual(originals.count(), 3)
        for line in originals:
            self.assertTrue(
                InventoryMovementLine.objects.filter(reversal_of=line).exists()
            )

    def test_batch_reverse_requires_officer(self):
        """A non-staff user cannot batch-reverse a group."""
        self._make_grouped_lines()
        self.client.login(username="clerk_actions", password="testpass")
        url = reverse(
            "batch_reverse_inventory_movement_lines", kwargs={"group_key": "grp123456"}
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            InventoryMovementLine.objects.filter(reversal_of__isnull=False).count(), 0
        )

    # --- deferred movement registration (§8) -------------------------------

    def test_register_deferred_movements_commodity_single_line(self):
        """Deferred registration of a COMMODITY item creates one line with the
        full quantity."""
        commodity = ProductTemplate.objects.create(
            name="Corn",
            nature=ProductTemplate.Nature.PRODUCT,
            sub_category="Feed",
            tracking_mode=ProductTemplate.TrackingMode.COMMODITY,
            default_unit="Kg",
            minimum_quantity=Decimal("0.01"),
        )
        commodity.entities.add(self.project)
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
            amount=Decimal("1000.00"),
        )
        item = make_invoice_item(
            purchase, commodity, quantity=Decimal("10.00"), unit_price=Decimal("100.00")
        )
        product = make_product(
            commodity, unit_price=Decimal("100.00"), quantity=10, entity=self.project
        )
        item.products.add(product)

        self.client.login(username="officer_actions", password="testpass")
        url = reverse(
            "register_deferred_movements", kwargs={"operation_pk": purchase.pk}
        )
        response = self.client.post(
            url, {"invoice_item": item.pk, "quantity": "10.00", "notes": ""}
        )

        self.assertRedirects(
            response,
            reverse("operation_detail_view", kwargs={"pk": purchase.pk}),
        )
        lines = InventoryMovementLine.objects.filter(operation=purchase)
        self.assertEqual(lines.count(), 1)
        self.assertEqual(lines.first().quantity, Decimal("10.00"))
        self.assertEqual(lines.first().product, product)
        self.assertTrue(lines.first().group_key)

    def test_register_deferred_movements_individual_one_line_per_product(self):
        """Deferred registration of an INDIVIDUAL item creates one line per
        product (qty=1 each) sharing a group key."""
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
            amount=Decimal("300.00"),
        )
        item = make_invoice_item(purchase, self.template, quantity=Decimal("3.00"))
        for _ in range(3):
            item.products.add(
                make_product(self.template, entity=self.project, quantity=1)
            )

        self.client.login(username="officer_actions", password="testpass")
        url = reverse(
            "register_deferred_movements", kwargs={"operation_pk": purchase.pk}
        )
        response = self.client.post(
            url, {"invoice_item": item.pk, "quantity": "3.00", "notes": ""}
        )

        self.assertRedirects(
            response,
            reverse("operation_detail_view", kwargs={"pk": purchase.pk}),
        )
        lines = InventoryMovementLine.objects.filter(operation=purchase)
        self.assertEqual(lines.count(), 3)
        self.assertTrue(all(ln.quantity == Decimal("1.00") for ln in lines))
        self.assertEqual(len({ln.group_key for ln in lines}), 1)

    def test_register_deferred_movements_requires_officer(self):
        """A non-staff user cannot register deferred movements."""
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
        )
        item = make_invoice_item(purchase, self.template, quantity=Decimal("1.00"))
        self.client.login(username="clerk_actions", password="testpass")
        url = reverse(
            "register_deferred_movements", kwargs={"operation_pk": purchase.pk}
        )

        response = self.client.post(
            url, {"invoice_item": item.pk, "quantity": "1.00", "notes": ""}
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            InventoryMovementLine.objects.filter(operation=purchase).count(), 0
        )

    # --- backward-compatible movement route (§8) ---------------------------

    def test_backward_compatible_movement_route_redirects(self):
        """The pre-split ``/movement/create/`` route redirects to the matching
        type-specific flow (purchase vs sale)."""
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
        )
        client_entity = make_entity(EntityType.PERSON, "Client", is_client=True)
        Stakeholder.objects.create(
            parent=self.project,
            target=client_entity,
            active=True,
            role=StakeholderRole.CLIENT,
        )
        sale = make_operation(
            source=client_entity,
            destination=self.project,
            officer=self.officer,
            proxy_class=SaleOperation,
            operation_type=OperationType.SALE,
        )
        self.client.login(username="officer_actions", password="testpass")
        url = reverse(
            "create_inventory_movement", kwargs={"operation_pk": purchase.pk}
        )

        response = self.client.get(url)
        self.assertRedirects(
            response,
            reverse(
                "create_purchase_movement", kwargs={"operation_pk": purchase.pk}
            ),
        )

        url = reverse("create_inventory_movement", kwargs={"operation_pk": sale.pk})
        response = self.client.get(url)
        self.assertRedirects(
            response,
            reverse("create_sale_movement", kwargs={"operation_pk": sale.pk}),
        )
