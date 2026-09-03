# Operations

> **Operation contracts:** Each per-operation spec is being widened into a **primary-source contract** that records **all possible branches** and **registers every affected business-logic file** (models, mixins, transaction types, views, templates) plus the tests that pin each branch. Where code and spec disagree, the spec is authoritative — fix the code, not the spec. The widened structure is defined in [_OPERATION_SPEC_TEMPLATE.md](_OPERATION_SPEC_TEMPLATE.md); **Cash Injection ([op_1](op_1_cash_injection.md)) is the worked example.** Remaining operations are being registered under the same structure.

## Core Operations
- [Op 1: Cash Injection](op_1_cash_injection.md)
- [Op 2: Cash Withdrawal](op_2_cash_withdrawal.md)
- [Op 3: Project Funding](op_3_project_funding.md)
- [Op 4: Project Refund](op_4_project_refund.md)

## Movement & Transfer
- [Op 5: Internal Transfer](op_5_internal_transfer.md)
- [Op 6: Loan](op_6_loan.md)

## Distribution & Adjustments
- [Op 7: Worker Advance](op_7_worker_advance.md)
- [Op 8: Expense](op_8_expense.md)
- [Op 9: Purchase](op_9_purchase.md)
- [Op 10: Sale](op_10_sale.md)
- [Op 11: Correction](op_11_correction.md)

## Inventory / Livestock
- [Op 12: Birth](op_12_birth.md)
- [Op 13: Death](op_13_death.md)
- [Op 14: Consumption](op_14_consumption.md)

## Valuation
- [Op 15: Capital Valuation (Gain & Loss)](op_15_capital_valuation.md)
