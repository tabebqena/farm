"""UI_CLAUSE_MANIFEST: spec clause -> UI test method registry.

Mirrors the executable COVERAGE_MANIFEST pattern used by the operation engine
suite (apps/app_operation/tests/base.py). The consistency test below fails the
build when a registered clause test is missing, keeping the suite from drifting
from the specs.

Each row: (spec_id, clause_id, test_module, method_name, visible_proxy)
"""
import importlib

from django.test import SimpleTestCase

UI_CLAUSE_MANIFEST = [
    # --- op_1 Cash Injection (docs/specs/operations/op_1_cash_injection.md) ---
    ("op_1", "VC1", "ui_tests.operations.test_cash_injection",
     "test_vc1_source_is_world", "create form locks source to World, no picker"),
    ("op_1", "VC7", "ui_tests.operations.test_cash_injection",
     "test_vc7_amount_positive", "error text on create form"),
    ("op_1", "SC6", "ui_tests.operations.test_cash_injection",
     "test_sc6_person_balance_increases", "balance badge + detail total"),
    ("op_1", "VR5", "ui_tests.operations.test_cash_injection",
     "test_vr5_reason_required", "error flash on reverse form"),
    ("op_1", "SR8", "ui_tests.operations.test_cash_injection",
     "test_sr8_person_balance_restored", "reversal alert + balance badge"),
    ("op_1", "SR9", "ui_tests.operations.test_cash_injection",
     "test_sr9_settlement_cleared", "reversal alert + Reversed badge"),
    # --- one-shot operations (ui_tests/operations/test_one_shot_operations.py) ---
    ("op_2", "SC", "ui_tests.operations.test_one_shot_operations",
     "CashWithdrawalUiTests.test_sc_create_success", "detail total"),
    ("op_2", "VC", "ui_tests.operations.test_one_shot_operations",
     "CashWithdrawalUiTests.test_vc_amount_positive", "error text"),
    ("op_2", "VR5", "ui_tests.operations.test_one_shot_operations",
     "CashWithdrawalUiTests.test_vr5_reason_required", "error flash"),
    ("op_2", "SR", "ui_tests.operations.test_one_shot_operations",
     "CashWithdrawalUiTests.test_sr_reverse_alert", "reversal alert"),
    ("op_3", "SC", "ui_tests.operations.test_one_shot_operations",
     "ProjectFundingUiTests.test_sc_create_success", "detail total"),
    ("op_3", "VC", "ui_tests.operations.test_one_shot_operations",
     "ProjectFundingUiTests.test_vc_amount_positive", "error text"),
    ("op_3", "VR5", "ui_tests.operations.test_one_shot_operations",
     "ProjectFundingUiTests.test_vr5_reason_required", "error flash"),
    ("op_3", "SR", "ui_tests.operations.test_one_shot_operations",
     "ProjectFundingUiTests.test_sr_reverse_alert", "reversal alert"),
    ("op_4", "SC", "ui_tests.operations.test_one_shot_operations",
     "ProjectRefundUiTests.test_sc_create_success", "detail total"),
    ("op_4", "VC", "ui_tests.operations.test_one_shot_operations",
     "ProjectRefundUiTests.test_vc_amount_positive", "error text"),
    ("op_4", "VR5", "ui_tests.operations.test_one_shot_operations",
     "ProjectRefundUiTests.test_vr5_reason_required", "error flash"),
    ("op_4", "SR", "ui_tests.operations.test_one_shot_operations",
     "ProjectRefundUiTests.test_sr_reverse_alert", "reversal alert"),
    ("op_7", "SC", "ui_tests.operations.test_one_shot_operations",
     "InternalTransferUiTests.test_sc_create_success", "detail total"),
    ("op_7", "VC", "ui_tests.operations.test_one_shot_operations",
     "InternalTransferUiTests.test_vc_amount_positive", "error text"),
    ("op_7", "VR5", "ui_tests.operations.test_one_shot_operations",
     "InternalTransferUiTests.test_vr5_reason_required", "error flash"),
    ("op_7", "SR", "ui_tests.operations.test_one_shot_operations",
     "InternalTransferUiTests.test_sr_reverse_alert", "reversal alert"),
    ("op_15", "SC", "ui_tests.operations.test_one_shot_operations",
     "CorrectionCreditUiTests.test_sc_create_success", "detail total"),
    ("op_15", "VC", "ui_tests.operations.test_one_shot_operations",
     "CorrectionCreditUiTests.test_vc_amount_positive", "error text"),
    ("op_15", "VR5", "ui_tests.operations.test_one_shot_operations",
     "CorrectionCreditUiTests.test_vr5_reason_required", "error flash"),
    ("op_15", "SR", "ui_tests.operations.test_one_shot_operations",
     "CorrectionCreditUiTests.test_sr_reverse_alert", "reversal alert"),
    ("op_15", "SC", "ui_tests.operations.test_one_shot_operations",
     "CorrectionDebitUiTests.test_sc_create_success", "detail total"),
    ("op_15", "VC", "ui_tests.operations.test_one_shot_operations",
     "CorrectionDebitUiTests.test_vc_amount_positive", "error text"),
    ("op_15", "VR5", "ui_tests.operations.test_one_shot_operations",
     "CorrectionDebitUiTests.test_vr5_reason_required", "error flash"),
    ("op_15", "SR", "ui_tests.operations.test_one_shot_operations",
     "CorrectionDebitUiTests.test_sr_reverse_alert", "reversal alert"),
]


class TestClauseManifestConsistency(SimpleTestCase):
    """Every manifest row must point at a real test method (drift guard)."""

    def test_manifest_methods_exist(self):
        missing = []
        for spec, clause, module, method, proxy in UI_CLAUSE_MANIFEST:
            mod = importlib.import_module(module)
            if "." in method:
                # "ClassName.method" form (methods may be inherited from a shared base)
                class_name, method_name = method.rsplit(".", 1)
                cls = getattr(mod, class_name, None)
                found = isinstance(cls, type) and hasattr(cls, method_name)
            else:
                found = any(
                    isinstance(getattr(mod, name), type)
                    and method in getattr(mod, name).__dict__
                    for name in dir(mod)
                )
            if not found:
                missing.append((spec, clause, module, method))
        self.assertEqual(
            missing,
            [],
            f"manifest rows missing a test method: {missing}",
        )
