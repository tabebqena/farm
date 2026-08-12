from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from apps.app_adjustment.models import Adjustment, AdjustmentType
from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import InventoryMovementLine
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
from apps.app_operation.models.period import FinancialPeriod, is_date_in_closed_period
from apps.app_operation.models.proxies import (
    CorrectionCreditOperation,
    PurchaseOperation,
    WorkerAdvanceOperation,
)

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
CLOSED_DAY = TODAY - timedelta(days=2)  # strictly inside [LAST_MONTH, YESTERDAY)
LAST_MONTH = TODAY - timedelta(days=30)


class DownstreamClosedPeriodGuardTest(TestCase):
    """
    Payments, repayments, movements and adjustments whose date falls inside a
    closed financial period of the operation's governing entity must be
    rejected (Fix 5).
    """

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_cp", is_staff=True)
        self.world = Entity.create(EntityType.WORLD)
        self.system = Entity.create(EntityType.SYSTEM)
        self.project = make_project_entity("ClosedGuard Farm")
        self.vendor = make_entity(EntityType.PERSON, "Vendor", is_vendor=True)
        Stakeholder.objects.create(
            parent=self.project,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        self.worker = Entity.create(EntityType.PERSON, name="Worker", is_worker=True)
        Stakeholder.objects.create(
            parent=self.project,
            target=self.worker,
            active=True,
            role=StakeholderRole.WORKER,
        )
        self.template = make_product_template("Calves")

        # The entity auto-creates an open period on creation; add a *closed*
        # period [LAST_MONTH, YESTERDAY) so a date inside it is guarded while
        # TODAY remains in the open one.
        FinancialPeriod.objects.create(
            entity=self.project, start_date=LAST_MONTH, end_date=YESTERDAY
        )

    def _fund_project(self, amount=Decimal("1000.00")):
        """Give the project balance via a system → project Correction Credit."""
        cc = CorrectionCreditOperation(
            source=self.system,
            destination=self.project,
            amount=amount,
            date=TODAY,
            officer=self.officer,
            operation_type=OperationType.CORRECTION_CREDIT,
        )
        cc.save()

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def test_helper_detects_closed_and_open_periods(self):
        self.assertTrue(is_date_in_closed_period(self.project, CLOSED_DAY))
        # The end date is excluded (half-open interval), and today is open.
        self.assertFalse(is_date_in_closed_period(self.project, YESTERDAY))
        self.assertFalse(is_date_in_closed_period(self.project, TODAY))
        self.assertFalse(is_date_in_closed_period(None, TODAY))

    # ------------------------------------------------------------------
    # Payment / repayment
    # ------------------------------------------------------------------

    def test_payment_rejected_in_closed_period(self):
        op = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
            amount=Decimal("500.00"),
        )
        with self.assertRaises(ValidationError):
            op.create_payment_transaction(
                amount=Decimal("10.00"), officer=self.officer, date=CLOSED_DAY
            )

    def test_repayment_rejected_in_closed_period(self):
        self._fund_project()
        op = make_operation(
            source=self.project,
            destination=self.worker,
            officer=self.officer,
            proxy_class=WorkerAdvanceOperation,
            operation_type=OperationType.WORKER_ADVANCE,
            amount=Decimal("100.00"),
        )
        with self.assertRaises(ValidationError):
            op.create_repayment_transaction(
                amount=Decimal("10.00"), officer=self.officer, date=CLOSED_DAY
            )

    # ------------------------------------------------------------------
    # Movement (view)
    # ------------------------------------------------------------------

    def test_movement_rejected_in_closed_period(self):
        op = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
            amount=Decimal("500.00"),
        )
        item = make_invoice_item(op, self.template, quantity=Decimal("5.00"))
        product = make_product(self.template, entity=self.project)
        item.products.add(product)

        self.client.login(username="officer_cp", password="testpass")
        url = reverse("create_purchase_movement", kwargs={"operation_pk": op.pk})
        self.client.post(
            url,
            {
                "date": CLOSED_DAY.isoformat(),
                "notes": "",
                "lines-TOTAL_FORMS": "1",
                "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
                "lines-0-invoice_item": item.pk,
                "lines-0-quantity": "5.00",
            },
        )
        self.assertFalse(
            InventoryMovementLine.objects.filter(operation=op).exists(),
            "No movement line should be created in a closed period",
        )

    # ------------------------------------------------------------------
    # Adjustment (view)
    # ------------------------------------------------------------------

    def test_adjustment_rejected_in_closed_period(self):
        op = make_operation(
            source=self.project,
            destination=self.vendor,
            officer=self.officer,
            proxy_class=PurchaseOperation,
            operation_type=OperationType.PURCHASE,
            amount=Decimal("500.00"),
        )
        url = reverse("record_accounting_adjustment", kwargs={"pk": op.pk})
        self.client.post(
            url,
            {
                "type": AdjustmentType.PURCHASE_DISCOUNT,
                "amount": "10.00",
                "reason": "test",
                "date": CLOSED_DAY.isoformat(),
            },
        )
        self.assertFalse(
            Adjustment.objects.filter(operation=op).exists(),
            "No adjustment should be created in a closed period",
        )
