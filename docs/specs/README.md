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
| 1 | Fund & Ledger Core | epic_1_fund_core.md |
| 2 | Operation Bugs & Missing Flows | epic_2_operation_bugs.md |
| 3 | Inventory & Invoice System | epic_3_inventory_invoice.md |
| 4 | Evaluation System | epic_4_evaluation.md |
| 5 | Entity & Stakeholder Management | epic_5_entity_stakeholder.md |
| 6 | Financial Categories | epic_6_financial_categories.md |
| 7 | Reporting & Dashboards *(future)* | epic_7_reporting.md |

---

## Operation Specs

| # | Operation | File |
|---|-----------|------|
| 1 | Cash Injection | [op_1_cash_injection.md](operations/op_1_cash_injection.md) |
| 2 | Cash Withdrawal | [op_2_cash_withdrawal.md](operations/op_2_cash_withdrawal.md) |
| 3 | Project Funding | [op_3_project_funding.md](operations/op_3_project_funding.md) |
| 4 | Project Refund | [op_4_project_refund.md](operations/op_4_project_refund.md) |
| 5/6 | Capital Valuation (Gain & Loss) | [op_20_capital_valuation_operation.md](operations/op_20_capital_valuation_operation.md) |
| 7 | Internal Transfer | [op_7_internal_transfer.md](operations/op_7_internal_transfer.md) |
| 8 | Loan | [op_8_loan.md](operations/op_8_loan.md) |
| 11 | Worker Advance | [op_11_worker_advance.md](operations/op_11_worker_advance.md) |
| 12 | Expense | [op_12_expense.md](operations/op_12_expense.md) |
| 13 | Purchase | [op_13_purchase.md](operations/op_13_purchase.md) |
| 14 | Sale | [op_14_sale.md](operations/op_14_sale.md) |
| 15 | Correction (Credit & Debit) | [op_15_correction.md](operations/op_15_correction.md) |

---

## Supporting Feature Specs

| Feature | File |
|---------|------|
| Adjustment | [adjustment.md](features/adjustment.md) |
| Financial Period | [financial_period.md](features/financial_period.md) |
| Stock (movement-based inventory) | [stock.md](features/stock.md) |
| Inventory Ledger | inventory_ledger.md |
| Financial Reports | [financial_reports.md](features/financial_reports.md) |
