"""Consolidated FinancialPeriod model tests."""

from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import InventoryMovementLine, ProductTemplate
from apps.app_inventory.stock import inventory_value
from apps.app_inventory.tests.general import (
    make_entity,
    make_invoice_item,
    make_operation,
    make_product,
    make_product_template,
)
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.period import FinancialPeriod
from apps.app_operation.models.proxies import (
    BirthOperation,
    CapitalGainOperation,
    CapitalLossOperation,
    ConsumptionOperation,
    DeathOperation,
    PurchaseOperation,
    SaleOperation,
)

# Module-level helpers


def _make_project(name="Test Project") -> Entity:
    """Create a PROJECT entity."""
    return Entity.create(EntityType.PROJECT, name=name)


def _make_person(name="Test Person") -> Entity:
    """Create a PERSON entity."""
    return Entity.create(EntityType.PERSON, name=name)


def _make_world() -> Entity:
    """Create a WORLD entity."""
    return Entity.create(EntityType.WORLD, name="World")


def _make_system() -> Entity:
    """Create a SYSTEM entity."""
    return Entity.create(EntityType.SYSTEM, name="System")


def _make_user(username="officer"):
    """Create a staff user to act as an operation officer."""
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        username=username, password="testpass", is_staff=True
    )


def _close_period(
    period: FinancialPeriod, days_ahead: int = 1
) -> "tuple[date, FinancialPeriod | None]":
    """Close a period using the close() method and return (end_date, next_period)."""
    end_date = date.today() + timedelta(days=days_ahead)
    next_period = period.close(end_date)
    return end_date, next_period


# Test classes


class PeriodAutoCreateTest(TestCase):
    """Auto-creation of periods when entities are created."""

    def test_person_entity_gets_auto_created_period(self):
        """A PERSON entity auto-gets a period on creation."""
        person = _make_person("Alice")
        period = person.financial_periods.first()
        self.assertIsNotNone(period)
        self.assertEqual(period.entity, person)

    def test_project_entity_gets_auto_created_period(self):
        """A PROJECT entity auto-gets a period on creation."""
        project = _make_project("Farm")
        period = project.financial_periods.first()
        self.assertIsNotNone(period)
        self.assertEqual(period.entity, project)

    def test_world_entity_does_not_get_period(self):
        """A WORLD entity does NOT get a period."""
        world = _make_world()
        self.assertEqual(world.financial_periods.count(), 0)

    def test_system_entity_does_not_get_period(self):
        """A SYSTEM entity does NOT get a period."""
        system = _make_system()
        self.assertEqual(system.financial_periods.count(), 0)

    def test_auto_period_start_date_equals_entity_created_at(self):
        """Auto-created period start_date matches entity.created_at.date()."""
        person = _make_person("Bob")
        period = person.financial_periods.first()
        self.assertEqual(period.start_date, person.created_at.date())


class PeriodLifecycleTest(TestCase):
    """Open/close lifecycle and state transitions."""

    def setUp(self):
        self.entity = _make_project("Farm")
        self.period = self.entity.financial_periods.first()

    def test_new_period_is_open(self):
        """Newly created period has end_date=None (open)."""
        self.assertIsNone(self.period.end_date)

    def test_close_sets_end_date(self):
        """Calling close() sets end_date."""
        end_date, _ = _close_period(self.period)
        self.period.refresh_from_db()
        self.assertEqual(self.period.end_date, end_date)

    def test_close_creates_next_period_for_active_entity(self):
        """close() auto-creates next period if entity is still active."""
        end_date = date.today() + timedelta(days=1)
        next_period = self.period.close(end_date)
        self.assertIsNotNone(next_period)
        self.assertEqual(next_period.entity, self.entity)
        self.assertEqual(next_period.start_date, end_date)
        self.period.refresh_from_db()
        self.assertEqual(self.period.end_date, end_date)

    def test_close_returns_none_for_inactive_entity(self):
        """close() returns None if entity is inactive."""
        self.entity.active = False
        self.entity.save()
        next_period = self.period.close()
        self.assertIsNone(next_period)

    def test_close_already_closed_raises(self):
        """Calling close() on already-closed period raises ValidationError."""
        _close_period(self.period)
        self.period.refresh_from_db()
        with self.assertRaises(ValidationError):
            self.period.close()

    def test_close_with_end_date_before_start_raises(self):
        """close(end_date) where end_date < start_date raises."""
        bad_end = self.period.start_date - timedelta(days=1)
        with self.assertRaises(ValidationError):
            self.period.close(bad_end)

    def test_close_with_end_date_equal_start_raises(self):
        """close(end_date) where end_date == start_date raises (clean_end_date)."""
        same_day = self.period.start_date
        with self.assertRaises(ValidationError):
            self.period.close(same_day)


class PeriodImmutabilityTest(TestCase):
    """Immutability constraints via ImmutableMixin."""

    def setUp(self):
        self.entity = _make_project("Farm")
        self.period = self.entity.financial_periods.first()

    def test_entity_is_immutable(self):
        """Changing entity field raises ValidationError."""
        new_entity = _make_project("Other")
        self.period.entity = new_entity
        with self.assertRaises(ValidationError):
            self.period.save()

    def test_start_date_is_immutable(self):
        """Changing start_date raises ValidationError."""
        self.period.start_date = date.today() + timedelta(days=1)
        with self.assertRaises(ValidationError):
            self.period.save()

    def test_end_date_can_be_set_from_none(self):
        """end_date can transition from None to a date (ALLOW_SET)."""
        end_date = date.today() + timedelta(days=1)
        self.period.end_date = end_date
        self.period.save()
        self.assertEqual(self.period.end_date, end_date)

    def test_end_date_cannot_be_changed_once_set(self):
        """Once set, end_date cannot be changed."""
        # Use close() directly instead of _close_period since close() auto-creates next period
        end_date = date.today() + timedelta(days=1)
        self.period.close(end_date)

        new_date = date.today() + timedelta(days=2)
        self.period.end_date = new_date
        with self.assertRaises(ValidationError):
            self.period.save()


class PeriodValidationTest(TestCase):
    """Overlap prevention and field validation."""

    def setUp(self):
        self.entity = _make_project("Farm")
        self.period1 = self.entity.financial_periods.first()

    def test_sequential_periods_allowed(self):
        """Two sequential periods (no overlap) is allowed."""
        end1 = date.today() + timedelta(days=1)
        self.period1.end_date = end1
        self.period1.save()

        period2 = FinancialPeriod.objects.create(
            entity=self.entity,
            start_date=end1,
        )
        period2.full_clean()
        period2.save()
        self.assertIsNotNone(period2.pk)

    def test_overlapping_periods_raises(self):
        """Two overlapping periods for same entity raises."""
        # Set up first period: today to tomorrow
        self.period1.end_date = date.today() + timedelta(days=1)
        self.period1.save()

        # Try to create overlapping second period
        period2 = FinancialPeriod(
            entity=self.entity,
            start_date=date.today(),
        )
        with self.assertRaises(ValidationError):
            period2.full_clean()

    def test_two_open_periods_raises(self):
        """Two open (end_date=None) periods for same entity raises."""
        period2 = FinancialPeriod(
            entity=self.entity,
            start_date=date.today() + timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            period2.full_clean()

    def test_cannot_create_period_for_inactive_entity(self):
        """Creating a new period for an inactive entity raises."""
        self.entity.active = False
        self.entity.save()

        period = FinancialPeriod(
            entity=self.entity,
            start_date=date.today(),
        )
        with self.assertRaises(ValidationError):
            period.full_clean()


class PeriodIsClosedTest(TestCase):
    """is_closed property boundary conditions."""


class EndAssetsMovementValueTest(TestCase):
    """
    ``end_assets`` = cash balance + movement-based inventory value + outstanding
    loan credits + outstanding worker advances paid.

    The inventory component is the movement-based valuation (`inventory_value()`
    in ``apps/app_inventory/stock.py``). Virtual value operations — Birth, Death,
    Capital Gain, Capital Loss — are non-cash: their ``*_PAYMENT`` transactions
    are excluded from ``payment_types()``, so their value appears exactly once,
    in movement-based inventory, never in the cash balance.
    """

    def setUp(self):
        self.project = _make_project("Farm")
        self.system = _make_system()
        self.officer = _make_user()
        # A vendor + Stakeholder relation is required by PurchaseOperation.
        self.vendor = make_entity(EntityType.PERSON, "Vendor", is_vendor=True)
        Stakeholder.objects.create(
            parent=self.project,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        self.period = self.project.financial_periods.first()
        # Close with a *future* end_date so new operations dated today remain
        # allowed (a period is only "truly closed" once end_date < today).
        self.end_date = date.today() + timedelta(days=1)
        self.period.close(self.end_date)

    # ------------------------------------------------------------------
    # Helpers — raw operations + real movement lines (movement-based valuation)
    # ------------------------------------------------------------------

    def _op(self, proxy_class, operation_type, source, destination, amount):
        return make_operation(
            source,
            destination,
            self.officer,
            proxy_class=proxy_class,
            operation_type=operation_type,
            amount=amount.quantize(Decimal("0.01")),
        )

    def _line(self, operation, product, qty):
        item = make_invoice_item(
            operation,
            product.product_template,
            quantity=qty,
            unit_price=product.unit_price,
        )
        return InventoryMovementLine.objects.create(
            operation=operation,
            invoice_item=item,
            product=product,
            quantity=qty,
            date=date.today(),
            officer=self.officer,
        )

    def _product(self, price, qty):
        return make_product(
            make_product_template(), unit_price=price, quantity=qty, entity=self.project
        )

    def _feed_template(self):
        """A consumable FEED product template (animals cannot be consumed)."""
        template = ProductTemplate.objects.create(
            name="Feed Mix",
            nature=ProductTemplate.Nature.FEED,
            sub_category="Feed",
            tracking_mode=ProductTemplate.TrackingMode.COMMODITY,
            default_unit="kg",
        )
        template.entities.add(self.project)
        return template

    def _purchase(self, qty, price, template=None):
        template = template or make_product_template()
        op = self._op(
            PurchaseOperation,
            OperationType.PURCHASE,
            self.project,
            self.vendor,
            qty * price,
        )
        product = make_product(
            template, unit_price=price, quantity=qty, entity=self.project
        )
        self._line(op, product, qty)
        return product

    # ------------------------------------------------------------------
    # Birth / Death / Capital — value counted exactly once, in inventory
    # ------------------------------------------------------------------

    def test_birth_counts_once_in_end_assets_via_inventory(self):
        """A birth is non-cash: the fund balance is unchanged and the born value
        appears exactly once in ``end_assets``, via movement-based inventory."""
        self.period.refresh_from_db()
        balance_before = self.project.balance
        assets_before = self.period.end_assets

        op = self._op(
            BirthOperation, OperationType.BIRTH, self.system, self.project,
            Decimal("500.00"),
        )
        self._line(op, self._product(Decimal("100.00"), 5), Decimal("5.00"))

        self.period.refresh_from_db()
        self.assertEqual(
            self.project.balance,
            balance_before,
            "Birth is non-cash — the fund balance must be unchanged.",
        )
        self.assertEqual(
            inventory_value(self.project, self.end_date), Decimal("500.00")
        )
        self.assertEqual(
            self.period.end_assets,
            assets_before + Decimal("500.00"),
            "Born value must be counted exactly once, via inventory.",
        )

    def test_consumption_reduces_end_assets_once_via_inventory(self):
        product = self._purchase(
            Decimal("10.00"), Decimal("100.00"), template=self._feed_template()
        )
        self.period.refresh_from_db()
        balance_before = self.project.balance
        assets_before = self.period.end_assets

        op = self._op(
            ConsumptionOperation,
            OperationType.CONSUMPTION,
            self.project,
            self.system,
            Decimal("300.00"),
        )
        self._line(op, product, Decimal("3.00"))

        self.period.refresh_from_db()
        self.assertEqual(self.project.balance, balance_before)
        self.assertEqual(
            inventory_value(self.project, self.end_date), Decimal("700.00")
        )
        self.assertEqual(
            self.period.end_assets,
            assets_before - Decimal("300.00"),
            "Consumption must reduce end_assets exactly once, via inventory.",
        )

    def test_death_reduces_end_assets_once_via_inventory(self):
        product = self._purchase(Decimal("10.00"), Decimal("100.00"))
        self.period.refresh_from_db()
        balance_before = self.project.balance
        assets_before = self.period.end_assets

        op = self._op(
            DeathOperation, OperationType.DEATH, self.project, self.system,
            Decimal("200.00"),
        )
        self._line(op, product, Decimal("2.00"))

        self.period.refresh_from_db()
        self.assertEqual(self.project.balance, balance_before)
        self.assertEqual(
            inventory_value(self.project, self.end_date), Decimal("800.00")
        )
        self.assertEqual(
            self.period.end_assets,
            assets_before - Decimal("200.00"),
            "Death must reduce end_assets exactly once, via inventory.",
        )

    def test_capital_gain_reflected_once_in_inventory_not_cash(self):
        product = self._purchase(Decimal("10.00"), Decimal("100.00"))
        self.period.refresh_from_db()
        balance_before = self.project.balance
        assets_before = self.period.end_assets

        op = self._op(
            CapitalGainOperation, OperationType.CAPITAL_GAIN, self.system, self.project,
            Decimal("500.00"),
        )
        item = make_invoice_item(
            op,
            product.product_template,
            quantity=Decimal("1.00"),
            unit_price=Decimal("500.00"),
        )
        product.invoice_items.add(item)

        self.period.refresh_from_db()
        self.assertEqual(self.project.balance, balance_before)
        self.assertEqual(
            inventory_value(self.project, self.end_date),
            Decimal("1500.00"),
            "Gain reflected once in inventory (carried 1000 + gain 500).",
        )
        self.assertEqual(self.period.end_assets, assets_before + Decimal("500.00"))

    def test_capital_loss_reflected_once_in_inventory_not_cash(self):
        product = self._purchase(Decimal("10.00"), Decimal("100.00"))
        self.period.refresh_from_db()
        balance_before = self.project.balance
        assets_before = self.period.end_assets

        op = self._op(
            CapitalLossOperation, OperationType.CAPITAL_LOSS, self.project, self.system,
            Decimal("200.00"),
        )
        item = make_invoice_item(
            op,
            product.product_template,
            quantity=Decimal("1.00"),
            unit_price=Decimal("200.00"),
        )
        product.invoice_items.add(item)

        self.period.refresh_from_db()
        self.assertEqual(self.project.balance, balance_before)
        self.assertEqual(
            inventory_value(self.project, self.end_date),
            Decimal("800.00"),
            "Loss reflected once in inventory (carried 1000 - loss 200).",
        )
        self.assertEqual(self.period.end_assets, assets_before - Decimal("200.00"))

    def test_sale_reduces_inventory_at_carried_cost(self):
        """Outbound sale movement is valued at carried cost, so inventory (and
        therefore ``end_assets``) reflects profit rather than the sale price."""
        product = self._purchase(Decimal("10.00"), Decimal("100.00"))
        self.period.refresh_from_db()
        assets_before = self.period.end_assets

        client = make_entity(EntityType.PERSON, "Client", is_client=True)
        Stakeholder.objects.create(
            parent=self.project,
            target=client,
            active=True,
            role=StakeholderRole.CLIENT,
        )
        op = self._op(
            SaleOperation, OperationType.SALE, client, self.project, Decimal("750.00")
        )
        self._line(op, product, Decimal("5.00"))

        self.period.refresh_from_db()
        self.assertEqual(
            inventory_value(self.project, self.end_date),
            Decimal("500.00"),
            "Sold stock is valued at its carried cost (5 × 100).",
        )
        self.assertEqual(
            self.period.end_assets,
            assets_before - Decimal("500.00"),
            "end_assets drops by carried cost, not the sale price.",
        )
