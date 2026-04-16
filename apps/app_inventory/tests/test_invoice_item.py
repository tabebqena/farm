from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import (
    InvoiceItem,
)
from apps.app_inventory.tests.general import (
    make_entity,
    make_invoice_item,
    make_operation,
    make_product_template,
    make_project_entity,
    make_user,
)

User = get_user_model()


class InvoiceItemTest(TestCase):
    def setUp(self):
        self.officer = make_user()
        self.vendor = make_entity(
            EntityType.PERSON, "Vendor", is_vendor=True, is_client=True
        )

        self.project = make_project_entity("Farm")
        Stakeholder.objects.create(
            parent=self.project,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )

        self.op = make_operation(self.project, self.vendor, self.officer)
        self.template = make_product_template()

    def test_total_price(self):
        item = make_invoice_item(
            self.op, self.template, Decimal("3"), Decimal("50.00")
        )
        self.assertEqual(item.total_price, Decimal("150.00"))

    def test_total_price_fractional_quantity(self):
        item = make_invoice_item(
            self.op, self.template, Decimal("2.5"), Decimal("40.00")
        )
        self.assertEqual(item.total_price, Decimal("100.00"))

    def test_clean_unit_price_negative_raises(self):
        item = InvoiceItem(
            operation=self.op,
            product=self.template,
            quantity=Decimal("1"),
            unit_price=Decimal("-10.00"),
        )
        with self.assertRaises(ValidationError):
            item.clean_unit_price()

    def test_clean_unit_price_zero_does_not_raise(self):
        # clean_unit_price only blocks negatives; zero unit price passes it
        item = InvoiceItem(
            operation=self.op,
            product=self.template,
            quantity=Decimal("1"),
            unit_price=Decimal("0.00"),
        )
        # Should not raise (zero is not < 0)
        item.clean_unit_price()

    def test_clean_quantity_zero_raises(self):
        # AmountCleanMixin checks _amount_name="quantity" > 0
        item = InvoiceItem(
            operation=self.op,
            product=self.template,
            quantity=Decimal("0"),
            unit_price=Decimal("10.00"),
        )
        with self.assertRaises(ValidationError):
            item.clean()

    def test_clean_quantity_negative_raises(self):
        item = InvoiceItem(
            operation=self.op,
            product=self.template,
            quantity=Decimal("-1"),
            unit_price=Decimal("10.00"),
        )
        with self.assertRaises(ValidationError):
            item.clean()

    def test_clean_valid_passes(self):
        item = InvoiceItem(
            operation=self.op,
            product=self.template,
            quantity=Decimal("2"),
            unit_price=Decimal("10.00"),
        )
        item.clean()  # should not raise

    def test_total_price_zero_unit_price(self):
        # total_price is a pure multiplication; zero unit_price is allowed
        item = InvoiceItem(
            operation=self.op,
            product=self.template,
            quantity=Decimal("5"),
            unit_price=Decimal("0.00"),
        )
        self.assertEqual(item.total_price, Decimal("0.00"))

    def test_clean_unit_price_positive_does_not_raise(self):
        item = InvoiceItem(
            operation=self.op,
            product=self.template,
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
        )
        item.clean_unit_price()  # should not raise

    def test_clean_does_not_enforce_unit_price(self):
        # clean() (AmountCleanMixin) only validates quantity; negative unit_price
        # must be caught by calling clean_unit_price() explicitly.
        item = InvoiceItem(
            operation=self.op,
            product=self.template,
            quantity=Decimal("1"),
            unit_price=Decimal("-5.00"),
        )
        item.clean()  # should not raise — unit_price is NOT checked here
