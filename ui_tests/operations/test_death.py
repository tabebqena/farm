"""UI happy-path tests for op_18 Death (docs/specs/operations/op_18_death.md).

Death is a stock event: it creates **no** transactions, auto-creates an outbound
movement line, and marks the written-off animal DEAD. Happy path per the repo
guidance: **create -> verify the write-off -> reverse**.

Prerequisites (dependency chain):
- an ACTIVE Project,
- an ACTIVE die-able ANIMAL product owned by the project (purchased + received
  via the canonical ``make_moved_product`` fixture).
"""
from decimal import Decimal

from apps.app_inventory.models import Product, ProductTemplate
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import DeathOperation

from ui_tests.base import UiTestCase
from ui_tests.operations.helpers import make_moved_product, make_product_template, make_vendor


class DeathUiTests(UiTestCase):
    """op_18 Death full happy path (write-off an existing animal)."""

    def _ready_animal(self):
        """An ACTIVE die-able bull owned by the project."""
        bull = make_product_template(
            self.project,
            name="Bull",
            nature=ProductTemplate.Nature.ANIMAL,
            default_unit="Head",
            minimum_quantity=Decimal("1.00"),
            sub_category="Cattle",
            has_tag=True,
            gender=ProductTemplate.Gender.MALE,
        )
        vendor = make_vendor(self.project, name="Livestock Vendor")
        animal = make_moved_product(
            self.project, bull, Decimal("1"), Decimal("400.00"), self.officer,
            vendor=vendor,
        )
        return animal

    def _latest_death(self) -> DeathOperation:
        from django.db.models import Q

        from apps.app_operation.models import Operation

        return Operation.objects.filter(
            Q(source=self.project) | Q(destination=self.project),
            operation_type=OperationType.DEATH,
        ).order_by("-created_at").cast()[0]  # type: ignore[attr-defined]

    def _create_death(self, animal, qty=Decimal("1"), price=Decimal("400.00")):
        self.login_as_officer()
        self.goto("death_create_view", self.project.pk)
        # Formset row 0: select the existing animal + qty/price.
        self.select("items-0-selected_product", animal.pk)
        self.fill_amount(qty, "items-0-quantity")
        self.fill_amount(price, "items-0-unit_price")
        self.click_submit()
        self.wait_for_url_contains("detail")
        return self._latest_death()

    def test_happy_path_create_and_reverse(self):
        """SC: the death records the operation with an auto outbound movement line,
        marks the animal DEAD and leaves the fund untouched. SR: reversing it
        restores the animal to ACTIVE."""
        animal = self._ready_animal()
        op = self._create_death(animal)

        # ── create effects (SC) ────────────────────────────────────────
        self.assert_flash_contains("recorded successfully")
        self.assert_visible_text("Death")
        self.assert_visible_text("400.00")          # operation total
        self.assert_visible_text("Inventory Movement Status")

        op.refresh_from_db()
        self.assertEqual(op.get_all_transactions().count(), 0, "death has no txs")
        self.assertEqual(op.items.count(), 1)  # type: ignore[attr-defined]
        self.assertEqual(op.movement_lines.count(), 1)  # type: ignore[attr-defined]

        # The animal is written off as DEAD.
        animal.refresh_from_db()
        self.assertEqual(animal.status, Product.Status.DEAD)

        # Death is non-cash — the project fund never moved.
        self.assert_fund_balance(self.project, Decimal("5000.00"))

        # ── reverse effects (SR) ───────────────────────────────────────
        self.reverse_operation(op, reason="UI death data entry error")
        self.assert_visible_text("Operation Voided (Reversed)")

        op.refresh_from_db()
        self.assertIsNotNone(op.reversed_by)
        animal.refresh_from_db()
        self.assertEqual(animal.status, Product.Status.ACTIVE)
