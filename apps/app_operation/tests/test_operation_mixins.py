"""
Structural tests for the Operation mixin split.

Birth / Death / Consumption / Capital Gain / Capital Loss are stock events, NOT
accounting operations: they must NOT inherit the issuance / payment / repayment /
adjustment mixins (no transactions, no settlement). The accounting operations must
retain theirs.
"""
from django.test import SimpleTestCase

from apps.app_operation.models.operation import Operation, StockEventMixin
from apps.app_operation.models.proxies import (
    BirthOperation,
    CapitalValuationOperation,
    CashInjectionOperation,
    CashWithdrawalOperation,
    ConsumptionOperation,
    CorrectionOperation,
    DeathOperation,
    ExpenseOperation,
    InternalTransferOperation,
    LoanOperation,
    ProjectFundingOperation,
    ProjectRefundOperation,
    PurchaseOperation,
    SaleOperation,
    WorkerAdvanceOperation,
)

NON_ACCOUNTING = (
    BirthOperation,
    DeathOperation,
    ConsumptionOperation,
    CapitalValuationOperation,
)
TRANSACTION_ONLY = (CashInjectionOperation,)
ADJUSTABLE = (PurchaseOperation, SaleOperation, ExpenseOperation)
REPAYABLE = (LoanOperation, WorkerAdvanceOperation)
ONE_SHOT = (
    CashInjectionOperation,
    CashWithdrawalOperation,
    ProjectFundingOperation,
    ProjectRefundOperation,
    InternalTransferOperation,
    CorrectionOperation,
    WorkerAdvanceOperation,
)

SETTLEMENT_MEMBERS = (
    "amount_settled",
    "is_fully_settled",
    "amount_remaining_to_settle",
    "create_payment_transaction",
    "create_issuance_transaction",
    "payment_transactions",
    "repayable_amount",
    "amount_repayed",
    "amount_remaining_to_repay",
)


class OperationMixinSeparationTest(SimpleTestCase):
    def test_non_accounting_ops_lack_accounting_members(self):
        """The 5 stock-event operations expose no settlement/transaction members."""
        for cls in NON_ACCOUNTING:
            for member in SETTLEMENT_MEMBERS:
                self.assertFalse(
                    hasattr(cls, member), f"{cls.__name__} still exposes {member}"
                )

    def test_non_accounting_ops_keep_core_operation_behaviour(self):
        """They still are Operations with inventory movement + reversal behaviour."""
        for cls in NON_ACCOUNTING:
            self.assertTrue(issubclass(cls, Operation), cls.__name__)
            self.assertTrue(hasattr(cls, "save_inventory"), cls.__name__)
            self.assertTrue(hasattr(cls, "reverse"), cls.__name__)
            self.assertTrue(hasattr(cls, "get_items_data"), cls.__name__)
            # effective_amount is a base fallback equal to the plain amount
            self.assertTrue(hasattr(cls, "effective_amount"), cls.__name__)

    def test_accounting_ops_retain_transaction_machinery(self):
        for cls in TRANSACTION_ONLY + ADJUSTABLE + REPAYABLE:
            self.assertTrue(hasattr(cls, "amount_settled"), cls.__name__)
            self.assertTrue(hasattr(cls, "create_issuance_transaction"), cls.__name__)
            self.assertTrue(hasattr(cls, "create_payment_transaction"), cls.__name__)

    def test_adjustable_ops_retain_adjustment_machinery(self):
        for cls in ADJUSTABLE:
            self.assertTrue(hasattr(cls, "effective_amount"), cls.__name__)

    def test_repayable_ops_retain_repayment_machinery(self):
        for cls in REPAYABLE:
            self.assertTrue(hasattr(cls, "repayable_amount"), cls.__name__)
            self.assertTrue(hasattr(cls, "is_fully_repayed"), cls.__name__)


class OneShotOperationConfigTest(SimpleTestCase):
    """One-shot proxies inherit their config from OneShotTransactionMixin."""

    def test_one_shot_proxies_inherit_one_shot_defaults(self):
        for cls in ONE_SHOT:
            self.assertTrue(cls._is_one_shot_operation, cls.__name__)
            self.assertEqual(cls.max_payment_transaction_count, 1, cls.__name__)
            self.assertFalse(cls.can_pay, cls.__name__)
            self.assertFalse(cls.is_partially_payable, cls.__name__)

    def test_non_one_shot_accounting_ops_are_not_one_shot(self):
        for cls in (ExpenseOperation, LoanOperation, PurchaseOperation, SaleOperation):
            self.assertFalse(cls._is_one_shot_operation, cls.__name__)

    def test_operation_exposes_public_is_one_shot_property(self):
        self.assertTrue(hasattr(Operation, "is_one_shot"))
        # The concrete Operation defaults to non-one-shot.
        self.assertFalse(Operation._is_one_shot_operation)


class StockEventMixinTest(SimpleTestCase):
    """Stock-event proxies inherit their config from ``StockEventMixin``."""

    STOCK_EVENTS = (
        BirthOperation,
        DeathOperation,
        ConsumptionOperation,
        CapitalValuationOperation,
    )
    INVOICE_STOCK_EVENTS = (BirthOperation, DeathOperation, ConsumptionOperation)

    def test_stock_events_inherit_stock_event_mixin(self):
        for cls in self.STOCK_EVENTS:
            self.assertTrue(issubclass(cls, StockEventMixin), cls.__name__)

    def test_stock_events_share_non_accounting_defaults(self):
        for cls in self.STOCK_EVENTS:
            self.assertFalse(cls.can_pay, cls.__name__)
            self.assertFalse(cls.is_partially_payable, cls.__name__)
            self.assertFalse(cls.check_balance_on_payment, cls.__name__)
            self.assertFalse(cls.has_category, cls.__name__)
            self.assertFalse(cls.has_repayment, cls.__name__)

    def test_invoice_stock_events_are_invoice_driven(self):
        for cls in self.INVOICE_STOCK_EVENTS:
            self.assertTrue(cls.has_invoice, cls.__name__)

    def test_capital_valuation_is_value_only(self):
        self.assertFalse(CapitalValuationOperation.has_invoice)
        self.assertTrue(CapitalValuationOperation.has_capital_valuation)

    def test_accounting_ops_are_not_stock_events(self):
        for cls in (ExpenseOperation, LoanOperation, PurchaseOperation, SaleOperation):
            self.assertFalse(issubclass(cls, StockEventMixin), cls.__name__)


class InventoryOperationApiTest(SimpleTestCase):
    """Every proxy exposes the inventory API via ``InventoryOperationMixin``."""

    def test_operation_exposes_inventory_api(self):
        for member in (
            "inventory_owner_entity",
            "inventory_receiving_entity",
            "can_create_movement",
            "save_inventory",
            "_auto_create_inventory_movements",
            "get_items_data",
        ):
            self.assertTrue(hasattr(Operation, member), member)

    def test_stock_events_inherit_inventory_api(self):
        for cls in StockEventMixinTest.STOCK_EVENTS:
            for member in ("get_items_data", "save_inventory", "can_create_movement"):
                self.assertTrue(hasattr(cls, member), f"{cls.__name__}.{member}")


class AdjustabilityConfigTest(SimpleTestCase):
    """``is_adjustable`` is the class flag; ``is_items_adjustable`` is derived.

    ``is_adjustable`` (accounting/amount adjustments) is set per proxy. The former
    ``can_adjust`` property duplicated it and was removed. ``is_items_adjustable``
    is now a property derived from ``has_invoice`` — item adjustments only apply
    to operations that carry invoice items (PURCHASE / SALE).
    """

    NON_ADJUSTABLE = (
        BirthOperation,
        DeathOperation,
        ConsumptionOperation,
        CapitalValuationOperation,
        LoanOperation,
        CashInjectionOperation,
        CashWithdrawalOperation,
        ProjectFundingOperation,
        ProjectRefundOperation,
        InternalTransferOperation,
        CorrectionOperation,
        WorkerAdvanceOperation,
    )

    def test_is_adjustable_flag_is_the_source_of_truth(self):
        for cls in ADJUSTABLE:
            self.assertTrue(cls.is_adjustable, cls.__name__)
        for cls in self.NON_ADJUSTABLE:
            self.assertFalse(cls.is_adjustable, cls.__name__)
        self.assertFalse(Operation.is_adjustable)

    def test_can_adjust_property_was_removed(self):
        # The accounting-adjustment view now guards on ``is_adjustable``.
        self.assertFalse(hasattr(Operation, "can_adjust"))
        for cls in ADJUSTABLE:
            self.assertFalse(hasattr(cls, "can_adjust"), cls.__name__)

    def test_is_items_adjustable_is_a_property(self):
        self.assertIsInstance(Operation.__dict__["is_items_adjustable"], property)
        for cls in ADJUSTABLE + self.NON_ADJUSTABLE:
            self.assertNotIn("is_items_adjustable", cls.__dict__, cls.__name__)

    def test_is_items_adjustable_derives_from_has_invoice(self):
        # Every proxy resolves is_items_adjustable == has_invoice on instances.
        from apps.app_operation.models.proxies import PROXY_MAP

        for cls in {*PROXY_MAP.values()}:
            op = cls()
            self.assertEqual(
                bool(op.is_items_adjustable),
                bool(cls.has_invoice),
                cls.__name__,
            )

