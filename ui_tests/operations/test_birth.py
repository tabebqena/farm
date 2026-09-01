"""UI happy-path tests for op_17 Birth (docs/specs/operations/op_17_birth.md).

Birth is a stock event: it creates **no** transactions, auto-creates inbound
movement lines, and lazily creates the newborn Product(s). Happy path per the
repo guidance: **create -> verify the newborn -> reverse**.

Prerequisites (dependency chain):
- an ACTIVE Project,
- an ANIMAL template that can give birth (FEMALE/MIXED + ``gives_birth_to``),
- an ACTIVE female/mixed animal owned by the project to act as the mother
  (purchased + received via the canonical ``make_moved_product`` fixture).
"""
from decimal import Decimal

from apps.app_inventory.models import Product, ProductTemplate
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import BirthOperation

from ui_tests.base import UiTestCase
from ui_tests.operations.helpers import make_moved_product, make_product_template, make_vendor


class BirthUiTests(UiTestCase):
    """op_17 Birth full happy path (mother -> newborn)."""

    def _ready_world(self):
        """A giving-birth template pair + an ACTIVE mother animal of the project."""
        calf = make_product_template(
            self.project,
            name="Calf",
            nature=ProductTemplate.Nature.ANIMAL,
            default_unit="Head",
            minimum_quantity=Decimal("1.00"),
            sub_category="Cattle",
            has_tag=True,
        )
        cow = make_product_template(
            self.project,
            name="Dairy Cow",
            nature=ProductTemplate.Nature.ANIMAL,
            default_unit="Head",
            minimum_quantity=Decimal("1.00"),
            sub_category="Cattle",
            has_tag=True,
            gender=ProductTemplate.Gender.FEMALE,
            gives_birth_to=calf,
        )
        vendor = make_vendor(self.project, name="Livestock Vendor")
        mother = make_moved_product(
            self.project, cow, Decimal("1"), Decimal("500.00"), self.officer,
            vendor=vendor,
        )
        return calf, mother

    def _latest_birth(self) -> BirthOperation:
        from django.db.models import Q

        from apps.app_operation.models import Operation

        return Operation.objects.filter(
            Q(source=self.project) | Q(destination=self.project),
            operation_type=OperationType.BIRTH,
        ).order_by("-created_at").cast()[0]  # type: ignore[attr-defined]

    def _create_birth(self, calf, mother, qty=Decimal("1"), price=Decimal("100.00")):
        self.login_as_officer()
        self.goto("birth_create_view", self.project.pk)
        # Formset row 0: newborn template, mother, gender; qty/price are
        # amount-input fields handled by the formatter.
        self.select("items-0-product_template", calf.pk)
        self.select("items-0-mother", mother.pk)
        self.select("items-0-gender", "MALE")
        self.fill_amount(qty, "items-0-quantity")
        self.fill_amount(price, "items-0-unit_price")
        self.click_submit()
        self.wait_for_url_contains("detail")
        return self._latest_birth()

    # ------------------------------------------------------------------
    # Happy path: create (stock event) + reverse
    # ------------------------------------------------------------------

    def test_happy_path_create_and_reverse(self):
        """SC: the birth records the operation with an auto inbound movement line,
        lazily creates the ACTIVE newborn, and creates no transactions. SR:
        reversing it removes the newborn from stock."""
        calf, mother = self._ready_world()
        op = self._create_birth(calf, mother)

        # ── create effects (SC) ────────────────────────────────────────
        self.assert_flash_contains("recorded successfully")
        self.assert_visible_text("Birth")
        self.assert_visible_text("100.00")          # operation total
        self.assert_visible_text("Inventory Movement Status")

        op.refresh_from_db()
        self.assertEqual(op.get_all_transactions().count(), 0, "birth has no txs")
        self.assertEqual(op.items.count(), 1)  # type: ignore[attr-defined]
        self.assertEqual(op.movement_lines.count(), 1)  # type: ignore[attr-defined]

        # The newborn is lazily created, ACTIVE, and belongs to the project.
        newborn = Product.objects.get(entity=self.project, product_template=calf)
        self.assertEqual(newborn.status, Product.Status.ACTIVE)
        self.assertIsNotNone(newborn.birth_date, "newborn carries its birth date")
        self.assertEqual(newborn.mother, mother)

        # Birth is non-cash — the project fund never moved.
        self.assert_fund_balance(self.project, Decimal("5000.00"))

        # ── reverse effects (SR) ───────────────────────────────────────
        self.reverse_operation(op, reason="UI birth data entry error")
        self.assert_visible_text("Operation Voided (Reversed)")

        op.refresh_from_db()
        self.assertIsNotNone(op.reversed_by)
        newborn.refresh_from_db()
        self.assertEqual(newborn.status, Product.Status.REMOVED)
