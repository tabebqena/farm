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
| 8 | Profit Distribution & Loss Coverage | [epic_8_profit_distribution.md](epic_8_profit_distribution.md) |

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
| 9 | Profit Distribution | [op_9_profit_distribution.md](op_9_profit_distribution.md) |
| 10 | Loss Coverage | [op_10_loss_coverage.md](op_10_loss_coverage.md) |
| 11 | Worker Advance | [op_11_worker_advance.md](op_11_worker_advance.md) |
| 12 | Expense | [op_12_expense.md](op_12_expense.md) |
| 13 | Purchase | [op_13_purchase.md](op_13_purchase.md) |
| 14 | Sale | [op_14_sale.md](op_14_sale.md) |
| 15 | Correction (Credit & Debit) | [op_15_correction.md](op_15_correction.md) |

---

## Supporting Feature Specs

| Feature | File |
|---------|------|
| Adjustment | [adjustment.md](adjustment.md) |
| Financial Period | [financial_period.md](financial_period.md) |

---

## Known Bugs (fix before anything else)

| # | File | Bug | Fix |
|---|------|-----|-----|
| 1 | `app_adjustment/apps.py` | `name = "app_adjustment"` | → `"apps.app_adjustment"` ✓ fixed |
| 2 | `app_evaluation/apps.py` | `name = "app_evaluation"` | → `"apps.app_evaluation"` ✓ fixed |
| 3 | `app_transaction/models.py` | `Transaction.clean()` blocks all ops | ✓ fixed (guard removed) |
| 4 | `reversal_alert.html` line 12 | `elif operation.is_reversed` | → `elif operation.is_reversal` ✓ fixed |
| 5 | `entity_detail.html` | `entity.perosn` typo | → `entity.person` ✓ fixed |
| 6 | `app_invoice/models.py` | `from app_base.models` wrong import | → `from apps.app_base.models` |
| 7 | `app_invoice/models.py` | `FK("Operation")` wrong label | → `FK("app_operation.Operation")` |
| 8 | `app_evaluation/models.py` | `FK("Product")` — model doesn't exist | Create `Product` in `app_inventory` |

---

## Suggested Start Order

```
Done:    Bug fixes 1–5 → python manage.py check passes
Done:    All 14 operation models + tests
Done:    DistributionPlan + ShareholderAllocation models + tests
Done:    Financial Period model + tests
Done:    Adjustment model + tests
Next:    Epic 3 (Inventory + Invoice) → Epic 4 (Evaluation + Product)
Then:    Epic 1.3 (Ledger history UI) + Epics 2, 5, 6 UI work
Future:  Epic 7 (Reporting)
```
