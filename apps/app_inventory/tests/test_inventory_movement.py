import json
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import (
    InventoryMovementLine,
    InvoiceItem,
    Product,
    ProductTemplate,
)
from apps.app_inventory.stock import active_lines_for_item, movement_state
from apps.app_inventory.tests.general import (
    make_entity,
    make_invoice_item,
    make_operation,
    make_product,
    make_product_template,
    make_project_entity,
    make_user,
)
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import (
    ConsumptionOperation,
    DeathOperation,
    PurchaseOperation,
    SaleOperation,
)


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
        """Test creating inventory movement lines for a PURCHASE operation.

        INDIVIDUAL tracking: one movement line per received animal (qty=1
        each), each lazily creating its own tagged Product — the "one line
        per purchased animal" contract.
        """
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
        )
        item = make_invoice_item(purchase, self.template, quantity=Decimal("5.00"))

        self.client.login(username="officer1", password="testpass")
        url = reverse("create_purchase_movement", kwargs={"operation_pk": purchase.pk})
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

        # One movement line per received animal, each qty 1.
        lines = InventoryMovementLine.objects.filter(operation=purchase)
        self.assertEqual(lines.count(), 3)
        self.assertTrue(all(ln.quantity == Decimal("1.00") for ln in lines))
        for ln in lines:
            self.assertEqual(ln.date, date.today())
            self.assertEqual(ln.notes, "Test movement")
            self.assertEqual(ln.officer, self.officer)
            self.assertEqual(ln.invoice_item, item)

        # Each line lazy-created its own tagged Product (one per animal).
        products = list(Product.objects.filter(invoice_items=item).order_by("pk"))
        self.assertEqual(len(products), 3)
        self.assertTrue(all(p.quantity == 1 for p in products))
        self.assertTrue(all(p.unique_id for p in products), "Every animal has a tag")

        # SE5/SE7 — each inbound movement materialises its product as ACTIVE
        # and the movement-based stock state is exactly the received qty.
        for ln in lines:
            ln.refresh_from_db()
            self.assertEqual(ln.product.status, Product.Status.ACTIVE)
            state = movement_state(ln.product, as_of=date.today())
            self.assertEqual(state["quantity"], Decimal("1.00"))

    def test_purchase_movement_creates_new_product_per_animal(self):
        """Registering a movement on an INDIVIDUAL purchase creates one new
        tagged Product per line instead of reusing the item's first product.

        Regression: a purchase (e.g. id 3) registered a movement but no new
        product line was created — every new line reused the first linked
        product, bypassing the lazy product creation in save()."""
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
        )
        item = make_invoice_item(purchase, self.template, quantity=Decimal("10.00"))

        # 4 heads already received at creation → 4 lines, 4 products.
        for _ in range(4):
            InventoryMovementLine.objects.create(
                operation=purchase,
                invoice_item=item,
                product=None,  # lazy-created by save()
                quantity=Decimal("1.00"),
                date=date.today(),
                officer=self.officer,
            )
        self.assertEqual(Product.objects.filter(invoice_items=item).count(), 4)

        # Receive the remaining 6 through the movement form.
        self.client.login(username="officer1", password="testpass")
        url = reverse("create_purchase_movement", kwargs={"operation_pk": purchase.pk})
        response = self.client.post(
            url,
            {
                "date": date.today().isoformat(),
                "notes": "More receipt",
                "lines-TOTAL_FORMS": "1",
                "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
                "lines-0-invoice_item": item.pk,
                "lines-0-quantity": "6.00",
            },
        )

        self.assertEqual(response.status_code, 302)

        # 10 movement lines (one per animal), each qty 1.
        lines = InventoryMovementLine.objects.filter(
            operation=purchase, reversal_of__isnull=True
        ).order_by("pk")
        self.assertEqual(lines.count(), 10)
        self.assertTrue(all(ln.quantity == Decimal("1.00") for ln in lines))

        # 10 tagged Products — the 6 new lines created 6 new products rather
        # than reusing the first product over and over.
        products = list(Product.objects.filter(invoice_items=item).order_by("pk"))
        self.assertEqual(len(products), 10)
        self.assertTrue(all(p.quantity == 1 for p in products))
        tags = [p.unique_id for p in products]
        self.assertTrue(all(tags), "Every animal has a tag")
        self.assertEqual(len(set(tags)), len(tags), "Tags must be unique")

    def test_non_staff_cannot_create_movement(self):
        """Test that non-staff users cannot create movements."""
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
        )

        self.client.login(username="non_officer", password="testpass")
        url = reverse("create_purchase_movement", kwargs={"operation_pk": purchase.pk})
        response = self.client.post(url)

        # Should redirect to entity_list
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            InventoryMovementLine.objects.filter(operation=purchase).exists(),
            "Non-staff should not be able to create movements",
        )

    def test_sale_operation_movement(self):
        """Test creating movement lines for a SALE operation."""
        sale = make_operation(
            source=self.client_entity,
            destination=self.project,
            officer=self.officer,
            proxy_class=SaleOperation,
            operation_type=OperationType.SALE,
        )
        item = make_invoice_item(sale, self.template, quantity=Decimal("10.00"))
        # The sold stock belongs to the selling project (the destination).
        product = make_product(self.template, entity=self.project)
        item.products.add(product)

        self.client.login(username="officer1", password="testpass")
        url = reverse("create_sale_movement", kwargs={"operation_pk": sale.pk})
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
        lines = InventoryMovementLine.objects.filter(operation=sale)
        self.assertEqual(lines.count(), 1)
        self.assertEqual(lines.first().quantity, Decimal("8.00"))

        # SE5 — the outbound movement is the only physical event; the product's
        # movement-based stock state reflects the dispatched quantity.
        line = lines.first()
        line.refresh_from_db()
        state = movement_state(line.product, as_of=date.today())
        self.assertEqual(state["quantity"], Decimal("-8.00"))

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
        url = reverse("create_purchase_movement", kwargs={"operation_pk": purchase.pk})
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
            InventoryMovementLine.objects.filter(operation=purchase).exists(),
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
        url = reverse("create_purchase_movement", kwargs={"operation_pk": purchase.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("formset", response.context)
        self.assertIn("operation", response.context)

    # ------------------------------------------------------------------
    # Stock ownership / location validation (Fix 1)
    # ------------------------------------------------------------------

    def _make_sale_with_product(self, product):
        sale = make_operation(
            source=self.client_entity,
            destination=self.project,
            officer=self.officer,
            proxy_class=SaleOperation,
            operation_type=OperationType.SALE,
        )
        item = make_invoice_item(sale, self.template, quantity=Decimal("10.00"))
        item.products.add(product)
        return sale, item

    def test_sale_movement_rejects_product_owned_by_another_entity(self):
        """A SALE movement line cannot move a product owned by another project."""
        other_project = make_project_entity("Other Farm")
        product = make_product(self.template, entity=other_project)
        sale, item = self._make_sale_with_product(product)

        line = InventoryMovementLine(
            operation=sale,
            invoice_item=item,
            product=product,
            quantity=Decimal("5.00"),
            date=date.today(),
            officer=self.officer,
        )
        with self.assertRaises(ValidationError):
            line.full_clean()

    def test_sale_movement_rejects_product_without_owner(self):
        """Outbound movement of an ownerless product is rejected."""
        product = make_product(self.template)  # entity=None
        sale, item = self._make_sale_with_product(product)

        line = InventoryMovementLine(
            operation=sale,
            invoice_item=item,
            product=product,
            quantity=Decimal("5.00"),
            date=date.today(),
            officer=self.officer,
        )
        with self.assertRaises(ValidationError):
            line.full_clean()

    def test_sale_movement_accepts_product_owned_by_selling_project(self):
        """A SALE movement line is valid when the product belongs to the selling project."""
        product = make_product(self.template, entity=self.project)
        sale, item = self._make_sale_with_product(product)

        line = InventoryMovementLine(
            operation=sale,
            invoice_item=item,
            product=product,
            quantity=Decimal("5.00"),
            date=date.today(),
            officer=self.officer,
        )
        line.full_clean()  # should not raise

    def test_purchase_lazy_product_belongs_to_project(self):
        """A PURCHASE lazily-created product is owned by the project (source)."""
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
        )
        item = make_invoice_item(purchase, self.template, quantity=Decimal("1.00"))
        line = InventoryMovementLine.objects.create(
            operation=purchase,
            invoice_item=item,
            product=None,  # lazy-created by save()
            quantity=Decimal("1.00"),
            date=date.today(),
            officer=self.officer,
        )
        line.refresh_from_db()
        self.assertIsNotNone(line.product)
        self.assertEqual(line.product.entity_id, self.project.pk)

    def test_outbound_owner_entity_delegates_to_operation(self):
        """Movement-line ownership delegates to the operation's canonical helper."""
        feed = ProductTemplate.objects.create(
            name="Feed Mix", nature=ProductTemplate.Nature.FEED, default_unit="Kg"
        )
        cases = [
            # (proxy, op_type, source, destination, expected owner, template)
            (
                SaleOperation,
                OperationType.SALE,
                self.client_entity,
                self.project,
                self.project,
                self.template,
            ),
            (
                DeathOperation,
                OperationType.DEATH,
                self.project,
                self.system,
                self.project,
                self.template,
            ),
            (
                ConsumptionOperation,
                OperationType.CONSUMPTION,
                self.project,
                self.system,
                self.project,
                feed,
            ),
        ]
        for proxy, op_type, source, destination, expected, template in cases:
            op = make_operation(source, destination, self.officer, proxy, op_type)
            line = InventoryMovementLine(
                operation=op,
                invoice_item=make_invoice_item(op, template),
                product=None,
                quantity=Decimal("1.00"),
            )
            self.assertEqual(line._outbound_owner_entity(), op.inventory_owner_entity)
            self.assertEqual(line._outbound_owner_entity(), expected)

    # ------------------------------------------------------------------
    # Inventory availability guard (Fix 2)
    # ------------------------------------------------------------------

    def _make_received_product(
        self, qty=Decimal("10.00"), price=Decimal("100.00"), template=None
    ):
        """Receive *qty* of the template into the project's stock via a PURCHASE
        movement, returning the physically-present product."""
        template = template or self.template
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
            amount=(qty * price).quantize(Decimal("0.01")),
        )
        item = make_invoice_item(purchase, template, quantity=qty, unit_price=price)
        product = make_product(
            template, unit_price=price, quantity=int(qty), entity=self.project
        )
        item.products.add(product)
        InventoryMovementLine.objects.create(
            operation=purchase,
            invoice_item=item,
            product=product,
            quantity=qty,
            date=date.today(),
            officer=self.officer,
        )
        return product

    def _outbound_line(self, proxy_cls, product, item_qty, move_qty, template=None):
        template = template or self.template
        amount = (item_qty * Decimal("100.00")).quantize(Decimal("0.01"))
        if proxy_cls is SaleOperation:
            op = make_operation(
                source=self.client_entity,
                destination=self.project,
                officer=self.officer,
                proxy_class=SaleOperation,
                operation_type=OperationType.SALE,
                amount=amount,
            )
        else:
            op = make_operation(
                source=self.project,
                destination=self.system,
                officer=self.officer,
                proxy_class=proxy_cls,
                operation_type=OperationType.DEATH
                if proxy_cls is DeathOperation
                else OperationType.CONSUMPTION,
                amount=amount,
            )
        item = make_invoice_item(op, template, quantity=item_qty)
        item.products.add(product)
        return InventoryMovementLine(
            operation=op,
            invoice_item=item,
            product=product,
            quantity=move_qty,
            date=date.today(),
            officer=self.officer,
        )

    def test_sale_movement_rejects_qty_beyond_on_hand(self):
        """A SALE of a physically-present product cannot dispatch more than on hand."""
        product = self._make_received_product(qty=Decimal("10.00"))
        line = self._outbound_line(SaleOperation, product, Decimal("15.00"), Decimal("12.00"))
        with self.assertRaises(ValidationError):
            line.full_clean()

    def test_death_movement_rejects_qty_beyond_on_hand(self):
        """A DEATH cannot write off more than the batch physically holds."""
        product = self._make_received_product(qty=Decimal("10.00"))
        line = self._outbound_line(DeathOperation, product, Decimal("12.00"), Decimal("12.00"))
        with self.assertRaises(ValidationError):
            line.full_clean()

    def test_consumption_movement_rejects_qty_beyond_on_hand(self):
        """A CONSUMPTION cannot consume more than the batch physically holds."""
        feed = ProductTemplate.objects.create(
            name="Feed Mix",
            nature=ProductTemplate.Nature.FEED,
            sub_category="Feed",
            default_unit="Kg",
        )
        product = self._make_received_product(qty=Decimal("10.00"), template=feed)
        line = self._outbound_line(
            ConsumptionOperation,
            product,
            Decimal("12.00"),
            Decimal("12.00"),
            template=feed,
        )
        with self.assertRaises(ValidationError):
            line.full_clean()

    def test_death_movement_accepts_qty_equal_to_on_hand(self):
        """A DEATH equal to the physically-held quantity is allowed."""
        product = self._make_received_product(qty=Decimal("10.00"))
        line = self._outbound_line(DeathOperation, product, Decimal("10.00"), Decimal("10.00"))
        line.full_clean()  # should not raise

    # ------------------------------------------------------------------
    # Unit / UOM consistency (Fix 4)
    # ------------------------------------------------------------------

    def test_invoice_item_rejects_quantity_not_multiple_of_minimum(self):
        """An invoice item cannot use a fraction of the template's minimum
        increment (Head templates have minimum_quantity = 1)."""
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
        )
        with self.assertRaises(ValidationError):
            make_invoice_item(purchase, self.template, quantity=Decimal("1.50"))

    def test_movement_rejects_quantity_not_multiple_of_minimum(self):
        """A movement line cannot use a fraction of the minimum increment."""
        product = self._make_received_product(qty=Decimal("10.00"))
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
            amount=Decimal("1000.00"),
        )
        item = make_invoice_item(purchase, self.template, quantity=Decimal("10.00"))
        line = InventoryMovementLine(
            operation=purchase,
            invoice_item=item,
            product=product,
            quantity=Decimal("1.50"),
            date=date.today(),
            officer=self.officer,
        )
        with self.assertRaises(ValidationError):
            line.full_clean()

    def test_movement_accepts_quantity_multiple_of_minimum(self):
        """A whole number of heads (multiple of 1) is allowed."""
        product = self._make_received_product(qty=Decimal("10.00"))
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
            amount=Decimal("1000.00"),
        )
        item = make_invoice_item(purchase, self.template, quantity=Decimal("10.00"))
        line = InventoryMovementLine(
            operation=purchase,
            invoice_item=item,
            product=product,
            quantity=Decimal("3.00"),
            date=date.today(),
            officer=self.officer,
        )
        line.full_clean()  # should not raise

    # ------------------------------------------------------------------
    # Receiving a partially-sold purchase (Fix: status must not block receipt)
    # ------------------------------------------------------------------

    def test_purchase_receive_remaining_after_partial_sale(self):
        """Receiving the remaining purchase qty is not blocked when the lot was
        partially dispatched (its Product is SOLD). Inbound receipts are
        independent of the lot's internal status — the purchase created the
        Product and receiving more simply re-stocks it."""
        commodity = ProductTemplate.objects.create(
            name="Feed Bags",
            nature=ProductTemplate.Nature.PRODUCT,
            sub_category="Feed",
            tracking_mode=ProductTemplate.TrackingMode.COMMODITY,
            default_unit="Bag",
        )
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
            amount=Decimal("1000.00"),
        )
        item = make_invoice_item(purchase, commodity, quantity=Decimal("10.00"))
        lot = make_product(
            commodity, unit_price=Decimal("100.00"), quantity=10, entity=self.project
        )
        item.products.add(lot)

        # Receive 1 of the 10.
        InventoryMovementLine.objects.create(
            operation=purchase,
            invoice_item=item,
            product=lot,
            quantity=Decimal("1.00"),
            date=date.today(),
            officer=self.officer,
        )

        # Sell 1 & move it — the same lot is dispatched, pushing its status to SOLD.
        sale = make_operation(
            source=self.client_entity,
            destination=self.project,
            officer=self.officer,
            proxy_class=SaleOperation,
            operation_type=OperationType.SALE,
            amount=Decimal("150.00"),
        )
        sale_item = make_invoice_item(sale, commodity, quantity=Decimal("10.00"))
        sale_item.products.add(lot)
        InventoryMovementLine.objects.create(
            operation=sale,
            invoice_item=sale_item,
            product=lot,
            quantity=Decimal("1.00"),
            date=date.today(),
            officer=self.officer,
        )
        lot.refresh_from_db()
        self.assertEqual(lot.status, Product.Status.SOLD)

        # Now receive the remaining 9 via the PURCHASE flow — must succeed.
        self.client.login(username="officer1", password="testpass")
        url = reverse("create_purchase_movement", kwargs={"operation_pk": purchase.pk})
        response = self.client.post(
            url,
            {
                "date": date.today().isoformat(),
                "notes": "Final receipt",
                "lines-TOTAL_FORMS": "1",
                "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
                "lines-0-invoice_item": item.pk,
                "lines-0-quantity": "9.00",
            },
        )

        self.assertEqual(response.status_code, 302)
        received = InventoryMovementLine.objects.filter(
            operation=purchase, reversal_of__isnull=True
        )
        self.assertEqual(received.count(), 2)
        self.assertEqual(
            received.aggregate(total=Sum("quantity"))["total"],
            Decimal("10.00"),
        )

        # The lot is back in stock: ACTIVE with the correct on-hand quantity.
        lot.refresh_from_db()
        self.assertEqual(lot.status, Product.Status.ACTIVE)
        state = movement_state(lot, as_of=date.today())
        self.assertEqual(state["quantity"], Decimal("9.00"))

    def test_sale_movement_rejects_operation_mismatch(self):
        """The SALE movement view rejects a PURCHASE operation (and vice versa)."""
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
        )
        self.client.login(username="officer1", password="testpass")
        url = reverse("create_sale_movement", kwargs={"operation_pk": purchase.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            InventoryMovementLine.objects.filter(operation=purchase).exists()
        )

        sale = make_operation(
            source=self.client_entity,
            destination=self.project,
            officer=self.officer,
            proxy_class=SaleOperation,
            operation_type=OperationType.SALE,
        )
        url = reverse("create_purchase_movement", kwargs={"operation_pk": sale.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            InventoryMovementLine.objects.filter(operation=sale).exists()
        )

    # ------------------------------------------------------------------
    # Reversal must reduce the operation's "received" figures (Fix:
    # after reversing a movement line the operation still showed the
    # items as received)
    # ------------------------------------------------------------------

    def _make_received_purchase(self):
        """PURCHASE of 10 heads received as 3 separate movement lines
        (4 + 4 + 2). Returns (purchase, item, product, lines)."""
        purchase = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
            amount=Decimal("1000.00"),
        )
        item = make_invoice_item(purchase, self.template, quantity=Decimal("10.00"))
        product = make_product(
            self.template,
            unit_price=Decimal("100.00"),
            quantity=10,
            entity=self.project,
        )
        item.products.add(product)
        lines = []
        for qty in (Decimal("4.00"), Decimal("4.00"), Decimal("2.00")):
            lines.append(
                InventoryMovementLine.objects.create(
                    operation=purchase,
                    invoice_item=item,
                    product=product,
                    quantity=qty,
                    date=date.today(),
                    officer=self.officer,
                )
            )
        return purchase, item, product, lines

    def test_get_items_data_excludes_reversed_movement_lines(self):
        """After reversing one movement line, get_items_data() reports the
        reduced active quantity (reversed originals no longer count as moved)
        and re-receiving the reversed amount is allowed."""
        purchase, item, product, lines = self._make_received_purchase()

        # Reverse the middle line (qty 4).
        lines[1].reverse(officer=self.officer)

        entry = purchase.get_items_data()[0]
        self.assertEqual(entry["moved_qty"], Decimal("6.00"))
        self.assertEqual(entry["remaining_qty"], Decimal("4.00"))
        self.assertFalse(entry["is_fully_moved"])
        # Only the active (non-reversed, non-reversal) lines are listed.
        self.assertEqual(entry["movement_lines"].count(), 2)

        # active_lines_for_item() mirrors the stock layer.
        active = active_lines_for_item(item)
        self.assertEqual(active.count(), 2)
        self.assertNotIn(lines[1], list(active))

        # The movement-form budget also accounts for the reversal.
        payload = InvoiceItem.build_movement_json(purchase)
        data = json.loads(payload)[str(item.pk)]
        self.assertEqual(Decimal(str(data["already_moved"])), Decimal("6.00"))
        self.assertEqual(Decimal(str(data["max_allowed"])), Decimal("4.00"))

        # Re-receiving the reversed quantity passes the over-delivery guard…
        re_receive = InventoryMovementLine(
            operation=purchase,
            invoice_item=item,
            product=product,
            quantity=Decimal("4.00"),
            date=date.today(),
            officer=self.officer,
        )
        re_receive.full_clean()  # should not raise

        # …but re-receiving more than the invoice budget still fails.
        over_receive = InventoryMovementLine(
            operation=purchase,
            invoice_item=item,
            product=product,
            quantity=Decimal("5.00"),
            date=date.today(),
            officer=self.officer,
        )
        with self.assertRaises(ValidationError):
            over_receive.full_clean()

    def test_operation_detail_shows_reduced_moved_qty_after_reversal(self):
        """The operation detail page reports the reduced received quantity
        after a movement line is reversed."""
        purchase, item, product, lines = self._make_received_purchase()
        lines[1].reverse(officer=self.officer)

        self.client.login(username="officer1", password="testpass")
        url = reverse("operation_detail_view", kwargs={"pk": purchase.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        entry = response.context["items_data"][0]
        self.assertEqual(entry["moved_qty"], Decimal("6.00"))
        self.assertEqual(entry["remaining_qty"], Decimal("4.00"))
