"""
Structural tests for the Operation mixin split.

Birth / Death / Consumption / Capital Gain / Capital Loss are stock events, NOT
accounting operations: they must NOT inherit the issuance / payment / repayment /
adjustment mixins (no transactions, no settlement). The accounting operations must
retain theirs.
"""
from django.test import SimpleTestCase

from apps.app_operation.models.operation import Operation
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
