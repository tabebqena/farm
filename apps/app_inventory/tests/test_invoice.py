from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, Stakeholder, StakeholderRole
from apps.app_inventory.models import Invoice
from apps.app_inventory.tests.general import (
    make_entity,
    make_invoice,
    make_invoice_item,
    make_operation,
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
    ExpenseOperation,
    PurchaseOperation,
    SaleOperation,
)


class InvoicePurchaseTest(TestCase):
    """
    Invoice attached to a Purchase operation.
    source = project, destination = vendor (registered as active vendor stakeholder).
    """

    def setUp(self):
        self.officer = make_user()
        self.vendor = make_entity("Vendor", is_vendor=True)
        self.project = make_project_entity("Farm")
        Stakeholder.objects.create(
            parent=self.project,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        self.op = make_operation(
            self.project,
            self.vendor,
            self.officer,
            PurchaseOperation,
            OperationType.PURCHASE,
        )
        self.template = make_product_template()

    # ------------------------------------------------------------------
    # total_price
    # ------------------------------------------------------------------

    def test_total_price_no_items(self):
        invoice = make_invoice(self.op)
        self.assertEqual(invoice.total_price, Decimal("0.00"))

    def test_total_price_single_item(self):
        invoice = make_invoice(self.op)
        make_invoice_item(invoice, self.template, Decimal("2"), Decimal("100.00"))
        self.assertEqual(invoice.total_price, Decimal("200.00"))

    def test_total_price_multiple_items(self):
        invoice = make_invoice(self.op)
        make_invoice_item(invoice, self.template, Decimal("2"), Decimal("100.00"))
        make_invoice_item(invoice, self.template, Decimal("3"), Decimal("50.00"))
        self.assertEqual(invoice.total_price, Decimal("350.00"))

    # ------------------------------------------------------------------
    # clean()
    # ------------------------------------------------------------------

    def test_clean_passes(self):
        invoice = make_invoice(self.op)
        invoice.clean()  # should not raise

    def test_clean_invalid_operation_type_raises(self):
        world = Entity.create(EntityType.WORLD)
        op = make_operation(
            self.project, world, self.officer, ExpenseOperation, OperationType.EXPENSE
        )
        invoice = Invoice(operation=op)
        with self.assertRaises(ValidationError):
            invoice.clean()


class InvoiceSaleTest(TestCase):
    """
    Invoice attached to a Sale operation.
    source = client, destination = project (client registered as active client stakeholder).
    """

    def setUp(self):
        self.officer = make_user()
        self.client_entity = make_entity("Client", is_client=True)
        self.project = make_project_entity("Farm")
        Stakeholder.objects.create(
            parent=self.project,
            target=self.client_entity,
            active=True,
            role=StakeholderRole.CLIENT,
        )
        self.op = make_operation(
            self.client_entity,
            self.project,
            self.officer,
            SaleOperation,
            OperationType.SALE,
        )

    def test_clean_passes(self):
        invoice = Invoice(operation=self.op)
        invoice.clean()  # should not raise


class InvoiceBirthTest(TestCase):
    """
    Invoice attached to a Birth operation.
    source = system entity, destination = project.
    """

    def setUp(self):
        self.officer = make_user()
        self.system = Entity.create(EntityType.SYSTEM)
        self.project = make_project_entity("Farm")
        self.op = make_operation(
            self.system,
            self.project,
            self.officer,
            BirthOperation,
            OperationType.BIRTH,
        )

    def test_clean_passes(self):
        invoice = Invoice(operation=self.op)
        invoice.clean()  # should not raise


class InvoiceDeathTest(TestCase):
    """
    Invoice attached to a Death operation.
    source = project, destination = system entity.
    """

    def setUp(self):
        self.officer = make_user()
        self.project = make_project_entity("Farm")
        self.system = Entity.create(EntityType.SYSTEM)
        self.op = make_operation(
            self.project,
            self.system,
            self.officer,
            DeathOperation,
            OperationType.DEATH,
        )

    def test_clean_passes(self):
        invoice = Invoice(operation=self.op)
        invoice.clean()  # should not raise


class InvoiceCapitalGainTest(TestCase):
    """
    Invoice attached to a Capital Gain operation.
    source = system entity, destination = project.
    """

    def setUp(self):
        self.officer = make_user()
        self.system = Entity.create(EntityType.SYSTEM)
        self.project = make_project_entity("Farm")
        self.op = make_operation(
            self.system,
            self.project,
            self.officer,
            CapitalGainOperation,
            OperationType.CAPITAL_GAIN,
        )

    def test_clean_passes(self):
        invoice = Invoice(operation=self.op)
        invoice.clean()  # should not raise


class InvoiceCapitalLossTest(TestCase):
    """
    Invoice attached to a Capital Loss operation.
    source = project, destination = system entity.
    """

    def setUp(self):
        self.officer = make_user()
        self.project = make_project_entity("Farm")
        self.system = Entity.create(EntityType.SYSTEM)
        self.op = make_operation(
            self.project,
            self.system,
            self.officer,
            CapitalLossOperation,
            OperationType.CAPITAL_LOSS,
        )

    def test_clean_passes(self):
        invoice = Invoice(operation=self.op)
        invoice.clean()  # should not raise
