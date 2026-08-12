# Operations

> **Cross-operation reference:** See [Operations Comparison — Validation & Success-Effects (per action)](operations-comparison.md) for the consolidated, **per-action** comparison (create / reverse / adjust / move items / adjust items / pay / repay): an action-applicability matrix, per-action validation matrices, per-action success-effects matrices, and per-operation × per-action reports. Not every operation accepts every action. Covers all 19 operation types.

> **Operation contracts:** Each per-operation spec is being widened into a **primary-source contract** that records **all possible branches** and **registers every affected business-logic file** (models, mixins, transaction types, views, templates) plus the tests that pin each branch. Where code and spec disagree, the spec is authoritative — fix the code, not the spec. The widened structure is defined in [_OPERATION_SPEC_TEMPLATE.md](_OPERATION_SPEC_TEMPLATE.md); **Cash Injection ([op_1](op_1_cash_injection.md)) is the worked example.** Remaining operations are being registered under the same structure.

## Core Operations
- [Op 1: Cash Injection](op_1_cash_injection.md)
- [Op 2: Cash Withdrawal](op_2_cash_withdrawal.md)
- [Op 3: Project Funding](op_3_project_funding.md)
- [Op 4: Project Refund](op_4_project_refund.md)
- [Op 5: Capital Gain](op_5_capital_gain.md)
- [Op 6: Capital Loss](op_6_capital_loss.md)

## Movement & Transfer
- [Op 7: Internal Transfer](op_7_internal_transfer.md)
- [Op 8: Loan](op_8_loan.md)

## Distribution & Adjustments
- [Op 9: Profit Distribution](op_9_profit_distribution.md)
- [Op 10: Loss Coverage](op_10_loss_coverage.md)
- [Op 11: Worker Advance](op_11_worker_advance.md)
- [Op 12: Expense](op_12_expense.md)
- [Op 13: Purchase](op_13_purchase.md)
- [Op 14: Sale](op_14_sale.md)
- [Op 15: Correction](op_15_correction.md)

## Inventory / Livestock
- [Op 17: Birth](op_17_birth.md)
- [Op 18: Death](op_18_death.md)
- [Op 19: Consumption](op_19_consumption.md)
