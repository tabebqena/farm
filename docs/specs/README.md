# Farm — Financial Management System
## Requirements & Feature Breakdown

> **How to use this document**
> Each feature is sized as a single coding session (~1–3 hours).
> Work top-to-bottom within each Epic. Don't skip ahead.

---

## System Overview

A Django-based financial management platform for a livestock farm business.
It tracks money flowing between **Entities** (people, projects, vendors, clients — an entity can act as both vendor and client across different relationships)
through **Operations** (business events) that generate **Transactions** (ledger entries)
against **Funds** (each entity's wallet). Supporting models handle invoices,
adjustments, inventory, and evaluations.

---

## Epics

| Epic | Title | File |
|------|-------|------|
| 1 | Fund & Ledger Core | [epic_1_fund_core.md](epic_1_fund_core.md) |
| 2 | Operation Bugs & Missing Flows | [epic_2_operation_bugs.md](epic_2_operation_bugs.md) |
| 3 | Inventory & Invoice System | [epic_3_inventory_invoice.md](epic_3_inventory_invoice.md) |
| 4 | Evaluation System | [epic_4_evaluation.md](epic_4_evaluation.md) |
| 5 | Entity & Stakeholder Management | [epic_5_entity_stakeholder.md](epic_5_entity_stakeholder.md) |
| 6 | Financial Categories | [epic_6_financial_categories.md](epic_6_financial_categories.md) |
| 7 | Reporting & Dashboards *(future)* | [epic_7_reporting.md](epic_7_reporting.md) |

---

## Operation Specs

| # | Operation | File |
|---|-----------|------|
| 1 | Cash Injection | [op_1_cash_injection.md](op_1_cash_injection.md) |
| 2 | Cash Withdrawal | [op_2_cash_withdrawal.md](op_2_cash_withdrawal.md) |
| 3 | Project Funding | [op_3_project_funding.md](op_3_project_funding.md) |
| 4 | Project Refund | [op_4_project_refund.md](op_4_project_refund.md) |
| 5 | Capital Gain | [op_5_capital_gain.md](op_5_capital_gain.md) |
| 6 | Capital Loss | [op_6_capital_loss.md](op_6_capital_loss.md) |
| 7 | Internal Transfer | [op_7_internal_transfer.md](op_7_internal_transfer.md) |
| 8 | Loan | [op_8_loan.md](op_8_loan.md) |
| 11 | Worker Advance | [op_11_worker_advance.md](op_11_worker_advance.md) |
| 12 | Expense | [op_12_expense.md](op_12_expense.md) |
| 13 | Purchase | [op_13_purchase.md](op_13_purchase.md) |
| 14 | Sale | [op_14_sale.md](op_14_sale.md) |
| 15 | Correction (Credit & Debit) | [op_15_correction.md](op_15_correction.md) |

---

## Supporting Feature Specs

| Feature | File |
|---------|------|
| Adjustment | [adjustment.md](features/adjustment.md) |
| Financial Period | [financial_period.md](features/financial_period.md) |
| Stock (movement-based inventory) | [stock.md](features/stock.md) |
| Inventory Ledger | [inventory_ledger.md](features/inventory_ledger.md) |
| Financial Reports | [financial_reports.md](features/financial_reports.md) |
