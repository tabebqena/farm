from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.forms import InvoiceItemCreateForm
from apps.app_inventory.models import (
    InventoryMovementLine,
    Product,
    ProductTemplate,
)
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
    BirthOperation,
    CapitalGainOperation,
    CapitalLossOperation,
    DeathOperation,
    PurchaseOperation,
    SaleOperation,
)


class ProductTest(TestCase):
    def setUp(self):
        self.officer = make_user()
        self.system = Entity.create(EntityType.SYSTEM)
        self.vendor = make_entity(EntityType.PERSON, "Vendor", is_vendor=True)
        self.project = make_project_entity("Farm")
        Stakeholder.objects.create(
            parent=self.project,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        self.client = make_entity(EntityType.PERSON, "Client", is_client=True)
        Stakeholder.objects.create(
            parent=self.project,
            target=self.client,
            active=True,
            role=StakeholderRole.CLIENT,
        )
        self.template = make_product_template()

    def _linked_product(
        self,
        proxy_class,
        op_type,
        source,
        destination,
        qty=Decimal("1"),
        price=Decimal("100.00"),
    ):
        """Create an operation → item → product chain and return the product."""
        op = make_operation(source, destination, self.officer, proxy_class, op_type)
        item = make_invoice_item(op, self.template, qty, price)
        product = make_product(self.template, price, int(qty))
        product.invoice_items.add(item)
        return product

    # --- status ---

    def test_status_active_no_invoice_items(self):
        product = make_product(self.template)
        self.assertEqual(product.status, Product.Status.ACTIVE)

    def test_status_active_after_purchase(self):
        product = self._linked_product(
            PurchaseOperation, OperationType.PURCHASE, self.project, self.vendor
        )
        self.assertEqual(product.status, Product.Status.ACTIVE)

    def test_status_sold_after_sale(self):
        product = self._linked_product(
            SaleOperation, OperationType.SALE, self.client, self.project
        )
        self.assertEqual(product.status, Product.Status.SOLD)

    def test_status_direction_aware_buyer_active_seller_sold(self):
        """A SALE is direction-aware: the buyer-owned copy is ACTIVE (received),
        the seller-owned copy is SOLD (dispatched)."""
        op = make_operation(
            self.client, self.project, self.officer, SaleOperation, OperationType.SALE
        )
        item = make_invoice_item(op, self.template, Decimal("1"), Decimal("100.00"))
        seller_product = make_product(self.template, Decimal("100.00"), 1, self.project)
        buyer_product = make_product(self.template, Decimal("100.00"), 1, self.client)
        seller_product.invoice_items.add(item)
        buyer_product.invoice_items.add(item)
        self.assertEqual(seller_product.status, Product.Status.SOLD)
        self.assertEqual(buyer_product.status, Product.Status.ACTIVE)

    def test_status_dead_after_death(self):
        product = self._linked_product(
            DeathOperation, OperationType.DEATH, self.project, self.system
        )
        self.assertEqual(product.status, Product.Status.DEAD)

    def test_status_dead_takes_priority_over_sold(self):
        sale_op = make_operation(
            self.client, self.project, self.officer, SaleOperation, OperationType.SALE
        )
        sale_item = make_invoice_item(sale_op, self.template)

        death_op = make_operation(
            self.project, self.system, self.officer, DeathOperation, OperationType.DEATH
        )
        death_item = make_invoice_item(death_op, self.template)

        product = make_product(self.template)
        product.invoice_items.add(sale_item, death_item)
        self.assertEqual(product.status, Product.Status.DEAD)

    # --- current_value (movement/ledger-based, reconciled with the ledger) ---

    def _make_valued_product(
        self,
        price=Decimal("100.00"),
        qty=1,
        capital_gain=Decimal("0"),
        capital_loss=Decimal("0"),
    ):
        """Create a product with a purchase movement (base value) and optional
        capital gain/loss operations — the basis used by ``Product.current_value``
        and the stock valuation."""
        purchase = make_operation(
            self.project,
            self.vendor,
            self.officer,
            PurchaseOperation,
            OperationType.PURCHASE,
            amount=(Decimal(qty) * price).quantize(Decimal("0.01")),
        )
        item = make_invoice_item(purchase, self.template, Decimal(qty), price)
        product = make_product(self.template, price, qty, self.project)
        product.invoice_items.add(item)
        InventoryMovementLine.objects.create(
            operation=purchase,
            invoice_item=item,
            product=product,
            quantity=Decimal(qty),
            date=date.today(),
            officer=self.officer,
            notes="",
            group_key="val",
        )
        if capital_gain:
            op = make_operation(
                self.system,
                self.project,
                self.officer,
                CapitalGainOperation,
                OperationType.CAPITAL_GAIN,
                amount=capital_gain,
            )
            item = make_invoice_item(op, self.template, Decimal(1), capital_gain)
            product.invoice_items.add(item)
        if capital_loss:
            op = make_operation(
                self.project,
                self.system,
                self.officer,
                CapitalLossOperation,
                OperationType.CAPITAL_LOSS,
                amount=capital_loss,
            )
            item = make_invoice_item(op, self.template, Decimal(1), capital_loss)
            product.invoice_items.add(item)
        return product

    def test_current_value_base_only(self):
        product = self._make_valued_product(Decimal("100.00"), 3)
        self.assertEqual(product.current_value, Decimal("300.00"))

    def test_current_value_adds_capital_gain(self):
        product = self._make_valued_product(
            Decimal("100.00"), 1, capital_gain=Decimal("20.00")
        )
        self.assertEqual(product.current_value, Decimal("120.00"))

    def test_current_value_subtracts_capital_loss(self):
        product = self._make_valued_product(
            Decimal("100.00"), 1, capital_loss=Decimal("15.00")
        )
        self.assertEqual(product.current_value, Decimal("85.00"))

    def test_current_value_gain_and_loss_combined(self):
        """base + gain - loss are applied together."""
        product = self._make_valued_product(
            Decimal("100.00"), 1, capital_gain=Decimal("30.00"), capital_loss=Decimal("10.00")
        )
        # 100 + 30 - 10 = 120
        self.assertEqual(product.current_value, Decimal("120.00"))

    def test_status_active_after_capital_gain(self):
        """A capital gain item does not change the status to SOLD or DEAD."""
        product = self._linked_product(
            CapitalGainOperation, OperationType.CAPITAL_GAIN, self.system, self.project
        )
        self.assertEqual(product.status, Product.Status.ACTIVE)

    def test_status_active_after_capital_loss(self):
        """A capital loss item does not change the status to SOLD or DEAD."""
        product = self._linked_product(
            CapitalLossOperation, OperationType.CAPITAL_LOSS, self.project, self.system
        )
        self.assertEqual(product.status, Product.Status.ACTIVE)

    def test_status_removed_after_reversed_birth(self):
        """A product whose only entry into stock was a BIRTH that has since been
        reversed is REMOVED (no longer in stock)."""
        op = make_operation(
            self.system, self.project, self.officer, BirthOperation, OperationType.BIRTH
        )
        product = make_product(self.template)
        product.invoice_items.add(make_invoice_item(op, self.template))
        self.assertEqual(product.status, Product.Status.ACTIVE)

        op.reverse(officer=self.officer)

        self.assertEqual(product.status, Product.Status.REMOVED)

    def test_status_sold_takes_priority_over_reversed_birth(self):
        """A born-then-sold animal stays SOLD even if the birth is later
        reversed (no resurrection of stock)."""
        birth_op = make_operation(
            self.system, self.project, self.officer, BirthOperation, OperationType.BIRTH
        )
        sale_op = make_operation(
            self.client, self.project, self.officer, SaleOperation, OperationType.SALE
        )
        product = make_product(self.template)
        product.invoice_items.add(make_invoice_item(birth_op, self.template))
        product.invoice_items.add(make_invoice_item(sale_op, self.template))
        self.assertEqual(product.status, Product.Status.SOLD)

        birth_op.reverse(officer=self.officer)

        self.assertEqual(product.status, Product.Status.SOLD)

    # --- validation ---

    def test_clean_negative_unit_price_raises(self):
        product = Product(
            product_template=self.template,
            unit_price=Decimal("-1.00"),
            quantity=1,
        )
        with self.assertRaises(ValidationError):
            product.clean()

    def test_clean_zero_unit_price_raises(self):
        """AmountCleanMixin rejects unit_price=0 (must be > 0)."""
        product = Product(
            product_template=self.template,
            unit_price=Decimal("0.00"),
            quantity=1,
        )
        with self.assertRaises(ValidationError):
            product.clean()

    # --- validate_active ---

    def test_validate_active_passes_for_active_product(self):
        product = make_product(self.template)
        # A fresh product is "obligated only" (not yet physically moved), which
        # is allowed for movement/reversal contexts.
        product.validate_active(allow_obligated=True)  # must not raise

    def test_validate_active_raises_for_sold_product(self):
        product = self._linked_product(
            SaleOperation, OperationType.SALE, self.client, self.project
        )
        self.assertEqual(product.status, Product.Status.SOLD)
        with self.assertRaises(ValidationError):
            product.validate_active()

    def test_validate_active_raises_for_dead_product(self):
        product = self._linked_product(
            DeathOperation,
            OperationType.DEATH,
            self.project,
            Entity.objects.get(entity_type="system"),
        )
        self.assertEqual(product.status, Product.Status.DEAD)
        with self.assertRaises(ValidationError):
            product.validate_active()

    def test_validate_active_raises_for_removed_product(self):
        op = make_operation(
            self.system, self.project, self.officer, BirthOperation, OperationType.BIRTH
        )
        product = make_product(self.template)
        product.invoice_items.add(make_invoice_item(op, self.template))
        op.reverse(officer=self.officer)
        self.assertEqual(product.status, Product.Status.REMOVED)

        with self.assertRaises(ValidationError):
            product.validate_active()
        # Allowed for reversals (restoring the removed animal's movement).
        product.validate_active(allow_reversal=True)  # must not raise


class ProductTagUniquenessTest(TestCase):
    """Birth / individual-tag identity rules (Fix 6)."""

    def setUp(self):
        self.officer = make_user()
        self.project = make_project_entity("Tag Farm")
        self.individual = ProductTemplate.objects.create(
            name="Tagged Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            tracking_mode=ProductTemplate.TrackingMode.INDIVIDUAL,
            default_unit="Head",
            has_tag=True,
        )
        self.individual.entities.add(self.project)

    def _form(self, uid, template=None):
        template = template or self.individual
        return InvoiceItemCreateForm(
            data={
                "product_template": str(template.pk),
                "quantity": "1",
                "unit_price": "100.00",
                "unique_id": uid,
                "description": "",
            },
            project=self.project,
        )

    def test_db_rejects_duplicate_tag_per_entity(self):
        Product.objects.create(
            product_template=self.individual,
            entity=self.project,
            unit_price=Decimal("100.00"),
            quantity=1,
            unique_id="TAG-1",
        )
        # The UniqueConstraint is validated by full_clean before insert, so a
        # duplicate surfaces as a ValidationError (friendly) rather than
        # reaching the DB as an IntegrityError.
        with self.assertRaises(ValidationError):
            Product.objects.create(
                product_template=self.individual,
                entity=self.project,
                unit_price=Decimal("100.00"),
                quantity=1,
                unique_id="TAG-1",
            )

    def test_db_allows_same_tag_across_entities(self):
        other = make_project_entity("Other Farm")
        Product.objects.create(
            product_template=self.individual,
            entity=self.project,
            unit_price=Decimal("100.00"),
            quantity=1,
            unique_id="TAG-1",
        )
        # Same tag under a different entity is allowed.
        Product.objects.create(
            product_template=self.individual,
            entity=other,
            unit_price=Decimal("100.00"),
            quantity=1,
            unique_id="TAG-1",
        )

    def test_form_auto_suggests_tag_for_individual_tracking(self):
        """A blank tag is auto-suggested (editable), so the form is valid."""
        form = self._form(uid="")
        self.assertTrue(form.is_valid())
        self.assertTrue(form.cleaned_data["unique_id"])
        self.assertTrue(
            form.cleaned_data["unique_id"].startswith(
                self.individual.effective_tag_prefix
            )
        )

    def test_form_rejects_duplicate_tag(self):
        Product.objects.create(
            product_template=self.individual,
            entity=self.project,
            unit_price=Decimal("100.00"),
            quantity=1,
            unique_id="TAG-1",
        )
        form = self._form(uid="TAG-1")
        self.assertFalse(form.is_valid())
        self.assertIn("unique_id", form.errors)
