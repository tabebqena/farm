"""Tests for purchasing from the World entity.

A World purchase is an ad-hoc one-off: the World acts as a vendor with no
Stakeholder record, the purchase is fully paid at creation, its payment cannot
be reversed on its own, and it cannot be adjusted.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from apps.app_adjustment.models import (
    Adjustment,
    AdjustmentType,
    InvoiceItemAdjustment,
    InvoiceItemAdjustmentType,
)
from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.models import ProductTemplate
from apps.app_operation.forms import PurchaseWizardStep1Form
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import PurchaseOperation
from apps.app_operation.tests.base import (
    BaseOperationTestCase,
    assert_derived_state_unchanged,
    snapshot_derived_state,
)
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


def _make_template(project, name="Feed Corn"):
    from apps.app_inventory.models import ProductTemplate as PT

    template = PT.objects.create(
        name=name,
        nature=PT.Nature.FEED,
        sub_category="Grain",
        tracking_mode=PT.TrackingMode.COMMODITY,
        default_unit="kg",
    )
    template.entities.add(project)
    return template


def _item(template_pk, quantity="10.00", unit_price="100.00"):
    return {
        "product_template_id": template_pk,
        "quantity": quantity,
        "unit_price": unit_price,
        "received_qty": "0",
        "description": "",
        "unique_id": "",
    }


def _session(world, total, items, amount_paid="0"):
    return {
        "date": date.today().isoformat(),
        "vendor_id": world.pk,
        "description": "World purchase",
        "total_amount": str(total),
        "amount_paid": str(amount_paid),
        "items": items,
    }


class WorldPurchaseCreateTest(BaseOperationTestCase):
    """The World is accepted as a vendor; full payment required at creation."""

    def setUp(self):
        super().setUp()
        self.template = _make_template(self.project)

    def _make_op(self, amount=Decimal("1000.00")):
        return PurchaseOperation(
            source=self.project,
            destination=self.world,
            amount=amount,
            operation_type=OperationType.PURCHASE,
            date=date.today(),
            description="World purchase",
            officer=self.officer,
        )

    # ------------------------------------------------------------------
    # Acceptance
    # ------------------------------------------------------------------

    def test_world_vendor_is_accepted(self):
        op = self._make_op()
        op.save()
        self.assertTrue(op.counterparty_is_world)
        self.assertEqual(
            op.get_all_transactions().get(
                type=TransactionType.PURCHASE_ISSUANCE
            ).target,
            self.world,
        )

    def test_get_related_entities_includes_world(self):
        related = PurchaseOperation.get_related_entities(self.project, {})
        self.assertIn(self.world, related)

    def test_wizard_vendor_queryset_includes_world(self):
        form = PurchaseWizardStep1Form(project=self.project)
        self.assertIn(self.world, form.fields["vendor"].queryset)

    def test_type_map_accepts_world_for_purchase(self):
        self.assertTrue(
            TransactionType.PURCHASE_ISSUANCE.is_allowed_entity_types(
                self.project, self.world
            )
        )
        self.assertTrue(
            TransactionType.PURCHASE_PAYMENT.is_allowed_entity_types(
                self.project, self.world
            )
        )

    # ------------------------------------------------------------------
    # Fully settled at creation
    # ------------------------------------------------------------------

    def test_create_from_session_full_payment_succeeds(self):
        session = _session(
            self.world,
            Decimal("1000.00"),
            [_item(self.template.pk)],
            amount_paid="1000.00",
        )
        op = PurchaseOperation.create_from_session(
            project=self.project, session_data=session, officer=self.officer
        )
        self.assertTrue(op.is_fully_settled)
        self.assertEqual(op.amount_remaining_to_settle, Decimal("0.00"))

    def test_create_from_session_zero_payment_rejected(self):
        session = _session(
            self.world,
            Decimal("1000.00"),
            [_item(self.template.pk)],
            amount_paid="0",
        )
        with self.assertRaises(ValidationError):
            PurchaseOperation.create_from_session(
                project=self.project, session_data=session, officer=self.officer
            )

    def test_create_from_session_partial_payment_rejected(self):
        session = _session(
            self.world,
            Decimal("1000.00"),
            [_item(self.template.pk)],
            amount_paid="400.00",
        )
        with self.assertRaises(ValidationError):
            PurchaseOperation.create_from_session(
                project=self.project, session_data=session, officer=self.officer
            )

    def test_process_payment_partial_rejected(self):
        op = self._make_op()
        op.save()
        with self.assertRaises(ValueError):
            op.process_payment(
                amount_paid=Decimal("400.00"),
                officer=self.officer,
                date=date.today(),
            )

    def test_create_payment_transaction_partial_rejected(self):
        op = self._make_op()
        op.save()
        with self.assertRaises(ValidationError):
            op.create_payment_transaction(
                amount=Decimal("400.00"),
                officer=self.officer,
                date=date.today(),
            )

    # ------------------------------------------------------------------
    # Reversal
    # ------------------------------------------------------------------

    def test_operation_reversal_reverses_issuance_and_payment(self):
        op = self._make_op()
        op.save()
        op.process_payment(
            amount_paid=Decimal("1000.00"),
            officer=self.officer,
            date=date.today(),
        )

        op.reverse(officer=self.officer)

        counters = op.get_all_transactions().filter(reversal_of__isnull=False)
        self.assertEqual(
            {c.type for c in counters},
            {TransactionType.PURCHASE_ISSUANCE, TransactionType.PURCHASE_PAYMENT},
        )

    def test_create_pay_reverse_leaves_world_unchanged(self):
        before = snapshot_derived_state()
        op = self._make_op()
        op.save()
        op.process_payment(
            amount_paid=Decimal("1000.00"),
            officer=self.officer,
            date=date.today(),
        )
        op.reverse(officer=self.officer)
        assert_derived_state_unchanged(self, before, msg="world purchase create+pay+reverse")


class WorldPurchaseViewTest(BaseOperationTestCase):
    """View-level behaviour: no-vendor project guard and payment reversal block."""

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.force_login(self.officer)
        self.template = _make_template(self.project)

    def _paid_world_purchase(self):
        op = PurchaseOperation(
            source=self.project,
            destination=self.world,
            amount=Decimal("1000.00"),
            operation_type=OperationType.PURCHASE,
            date=date.today(),
            description="World purchase",
            officer=self.officer,
        )
        op.save()
        op.process_payment(
            amount_paid=Decimal("1000.00"),
            officer=self.officer,
            date=date.today(),
        )
        return op

    def test_wizard_available_without_vendor_stakeholders(self):
        """A project with no vendors can still start a purchase (World offered)."""
        # self.project has no vendor Stakeholders in this fixture.
        response = self.client.get(
            reverse("purchase_wizard_step1", kwargs={"pk": self.project.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_world_payment_detail_hides_reverse(self):
        op = self._paid_world_purchase()
        payment = op.get_all_transactions().get(type=TransactionType.PURCHASE_PAYMENT)
        response = self.client.get(
            reverse("transaction_detail", kwargs={"transaction_pk": payment.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_reverse"])

    def test_world_payment_cannot_be_reversed_alone(self):
        op = self._paid_world_purchase()
        payment = op.get_all_transactions().get(type=TransactionType.PURCHASE_PAYMENT)
        response = self.client.post(
            reverse("transaction_reverse_view", kwargs={"pk": payment.pk})
        )
        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.assertFalse(payment.is_reversed)


class WorldPurchaseAdjustmentBlockTest(BaseOperationTestCase):
    """Adjustments are blocked on a World purchase (model + item)."""

    def setUp(self):
        super().setUp()
        self.op = PurchaseOperation(
            source=self.project,
            destination=self.world,
            amount=Decimal("1000.00"),
            operation_type=OperationType.PURCHASE,
            date=date.today(),
            description="World purchase",
            officer=self.officer,
        )
        self.op.save()

    def test_accounting_adjustment_blocked(self):
        adj = Adjustment(
            operation=self.op,
            type=AdjustmentType.PURCHASE_GENERAL_INCREASE,
            amount=Decimal("100.00"),
            reason="Test",
            date=date.today(),
            officer=self.officer,
        )
        with self.assertRaises(ValidationError):
            adj.full_clean()

    def test_item_adjustment_blocked(self):
        item_adj = InvoiceItemAdjustment(
            operation=self.op,
            type=InvoiceItemAdjustmentType.PURCHASE_ITEM_INCREASE,
            date=date.today(),
            officer=self.officer,
        )
        with self.assertRaises(ValidationError):
            item_adj.full_clean()
