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
| 1 | Fund & Ledger Core | [epic_1_fund_ledger.md](epic_1_fund_ledger.md) |
| 2 | Operation Bugs & Missing Flows | [epic_2_operation_bugs.md](epic_2_operation_bugs.md) |
| 3 | Inventory & Invoice System | [epic_3_inventory_invoice.md](epic_3_inventory_invoice.md) |
| 4 | Evaluation System | [epic_4_evaluation.md](epic_4_evaluation.md) |
| 5 | Entity & Stakeholder Management | [epic_5_entity_stakeholder.md](epic_5_entity_stakeholder.md) |
| 6 | Financial Categories | [epic_6_financial_categories.md](epic_6_financial_categories.md) |
| 7 | Reporting & Dashboards *(future)* | [epic_7_reporting.md](epic_7_reporting.md) |

---

## Known Bugs (fix before anything else)

| # | File | Bug | Fix |
|---|------|-----|-----|
| 1 | `app_adjustment/apps.py` | `name = "app_adjustment"` | → `"apps.app_adjustment"` |
| 2 | `app_evaluation/apps.py` | `name = "app_evaluation"` | → `"apps.app_evaluation"` |
| 3 | `app_transaction/models.py` | `Transaction.clean()` blocks all ops | Remove bad `DOCUMENT_TYPE_MAP` guard |
| 4 | `reversal_alert.html` line 12 | `elif operation.is_reversed` | → `elif operation.is_reversal` |
| 5 | `entity_detail.html` | `entity.perosn` typo | → `entity.person` |
| 6 | `app_invoice/models.py` | `from app_base.models` wrong import | → `from apps.app_base.models` |
| 7 | `app_invoice/models.py` | `FK("Operation")` wrong label | → `FK("app_operation.Operation")` |
| 8 | `app_evaluation/models.py` | `FK("Product")` — model doesn't exist | Create `Product` in `app_inventory` |

---

## Suggested Start Order

```
Week 1:  Bug fixes (all 8 above) → python manage.py check passes
Week 2:  Epic 1 (Fund balance + Transaction validation)
Week 3:  Epic 3.1–3.3 (Inventory + Invoice fixes)
Week 4:  Epic 4 (Evaluation + Product)
Week 5+: Epics 2, 5, 6 in any order
Future:  Epic 7 (Reporting)
```
