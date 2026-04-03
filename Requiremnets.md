# Farm — Financial Management System
## Requirements & Feature Breakdown

> **How to use this document**
> Each feature is sized as a single coding session (~1–3 hours).
> Work top-to-bottom within each Epic. Don't skip ahead.

---

## System Overview

A Django-based financial management platform for a livestock farm business.
It tracks money flowing between **Entities** (people, projects, vendors, clients)
through **Operations** (business events) that generate **Transactions** (ledger entries)
against **Funds** (each entity's wallet). Supporting models handle invoices,
adjustments, inventory, and evaluations.

---

## EPIC 1 — Fund & Ledger Core
> The heart of the system. Everything else depends on this being correct.

### Feature 1.1 — Fund Balance Computation
**Goal:** `fund.balance` returns the correct net value of a fund at any point.

Tasks:
- [ ] Add `balance` property to `Fund` model: sum of `transactions_incoming.amount` minus `transactions_outgoing.amount`, excluding reversed/reversal transactions
- [ ] Add `balance_as_of(date)` method for historical balance queries
- [ ] Write unit tests: empty fund = 0, injection increases balance, withdrawal decreases it, reversed tx is excluded

### Feature 1.2 — Transaction.clean() Validation
**Goal:** The `Transaction.clean()` method currently blocks *all* transactions with a wrong check. Fix it.

Tasks:
- [*] Remove or fix the `DOCUMENT_TYPE_MAP` guard in `Transaction.clean()` — currently raises `ValidationError` for all valid operation types
- [ ] Expand `DOCUMENT_TYPE_MAP` to include all 14 operation types and their allowed transaction types (use `OperationType.MAP()` as source of truth)
- [ ] Re-enable `clean_type()` body (currently has an early `return` that skips all validation)
- [ ] Write a test that saves a `PURCHASE_PAYMENT` transaction on a `PURCHASE` operation — should pass

### Feature 1.3 — Ledger History Tab in Entity Detail
**Goal:** The entity detail page has a "Ledger History" tab that currently says "coming soon". Make it real.

Tasks:
- [ ] Add a view that returns all transactions for a given entity's fund (both incoming and outgoing)
- [ ] Wire the view into `entity_detail.html`
- [ ] Show: date, type, amount, direction (in/out), counterparty fund, linked document
- [ ] Paginate — 25 rows per page

### Feature 1.3 — Shared Views: record_payment_transaction & record_repayment_transaction
**Goal:** Fix the broken `record_transaction_payment` view and verify `record_transaction_repayment` works correctly.

**Known bug in `record_transaction_payment`:**
- Line 20: `operation.create_payment_transaction` is referenced but never called (no parentheses, dead code).
- Source/target funds are **reversed**: current code uses `destination.fund → source.fund` but payment should flow `source.fund → destination.fund` (project pays vendor, not the other way).

Tasks:
- [ ] Fix fund direction in `record_transaction_payment`: `source=operation.source.fund`, `target=operation.destination.fund`
- [ ] Remove the dead `operation.create_payment_transaction` line
- [ ] Verify `record_transaction_repayment` fund direction is correct: repayment flows `destination.fund → source.fund` (debtor/worker repays back to source)
- [ ] Verify the `amount_remaining_to_repay` property exists on the proxy models that use repayment (LOAN, WORKER_ADVANCE)
- [ ] Manual test: record a payment on a PURCHASE — funds should move project → vendor

---

### Feature 1.4 — Cash Injection Operation
**Type:** One-shot (issuance = payment, no separate payment step)
**Transaction flow:**
- Issuance: `world.fund → person.fund` — type: `CAPITAL_INJECTION_ISSUANCE`
- Payment: `world.fund → person.fund` — type: `CAPITAL_INJECTION_PAYMENT`

Tasks:
- [ ] Verify issuance transaction is created on save with correct source/target direction
- [ ] Verify reversal creates counter-transactions: `person.fund → world.fund`
- [ ] UI: create form — source must be World entity, destination must be a Person
- [ ] UI: operation detail shows issuance transaction and reversal button

---

### Feature 1.5 — Cash Withdrawal Operation
**Type:** One-shot
**Transaction flow:**
- Issuance: `person.fund → world.fund` — type: `CAPITAL_WITHDRAWAL_ISSUANCE`
- Payment: `person.fund → world.fund` — type: `CAPITAL_WITHDRAWAL_PAYMENT`

Tasks:
- [ ] Verify issuance transaction created with correct direction (person → world)
- [ ] Verify reversal: `world.fund → person.fund`
- [ ] UI: create form — source must be Person, destination must be World entity
- [ ] UI: operation detail shows issuance transaction and reversal button

---

### Feature 1.6 — Project Funding Operation
**Type:** One-shot
**Transaction flow:**
- Issuance: `person.fund → project.fund` — type: `PROJECT_FUNDING_ISSUANCE`
- Payment: `person.fund → project.fund` — type: `PROJECT_FUNDING_PAYMENT`

Tasks:
- [ ] Verify issuance transaction created with correct direction (funder → project)
- [ ] Verify reversal: `project.fund → person.fund`
- [ ] UI: create form — destination must be a Project entity
- [ ] UI: operation detail shows issuance transaction, funder and project labels, reversal button

---

### Feature 1.7 — Project Refund Operation
**Type:** One-shot
**Transaction flow:**
- Issuance: `project.fund → person.fund` — type: `PROJECT_REFUND_ISSUANCE`
- Payment: `project.fund → person.fund` — type: `PROJECT_REFUND_PAYMENT`

Tasks:
- [ ] Verify issuance transaction created with correct direction (project → funder)
- [ ] Verify reversal: `person.fund → project.fund`
- [ ] UI: create form — source must be a Project entity
- [ ] UI: operation detail shows issuance transaction and reversal button

---

### Feature 1.8 — Profit Distribution Operation
**Type:** One-shot
**Transaction flow:**
- Issuance: `project.fund → shareholder.fund` — type: `PROFIT_DISTRIBUTION_ISSUANCE`
- Payment: `project.fund → shareholder.fund` — type: `PROFIT_DISTRIBUTION_PAYMENT`

Tasks:
- [ ] Verify issuance transaction created with correct direction (project → shareholder)
- [ ] Verify reversal: `shareholder.fund → project.fund`
- [ ] UI: create form — source must be Project, destination must be Shareholder
- [ ] UI: operation detail shows issuance transaction and reversal button

---

### Feature 1.9 — Loss Coverage Operation
**Type:** One-shot
**Transaction flow:**
- Issuance: `shareholder.fund → project.fund` — type: `LOSS_COVERAGE_ISSUANCE`
- Payment: `shareholder.fund → project.fund` — type: `LOSS_COVERAGE_PAYMENT`

Tasks:
- [ ] Verify issuance transaction created with correct direction (shareholder → project)
- [ ] Verify reversal: `project.fund → shareholder.fund`
- [ ] UI: create form — source is Shareholder, destination is Project
- [ ] UI: operation detail shows issuance transaction and reversal button

---

### Feature 1.10 — Internal Transfer Operation
**Type:** One-shot (both source and destination must be internal entities)
**Transaction flow:**
- Issuance: `source.fund → destination.fund` — type: `INTERNAL_TRANSFER_ISSUANCE`
- Payment: `source.fund → destination.fund` — type: `INTERNAL_TRANSFER_PAYMENT`

Tasks:
- [ ] Verify issuance transaction created with correct direction
- [ ] Verify both source and destination are flagged as internal (`is_internal=True`)
- [ ] Verify reversal: `destination.fund → source.fund`
- [ ] UI: create form — entity dropdowns filtered to internal entities only
- [ ] UI: operation detail shows issuance transaction and reversal button

---

### Feature 1.11 — Loan Operation
**Type:** Has repayment (`has_repayment=True`, `max_payment_count=-1`)
**Transaction flow:**
- Issuance: `creditor.fund → debtor.fund` — type: `LOAN_ISSUANCE`
- Payment (loan disbursement): `creditor.fund → debtor.fund` — type: `LOAN_PAYMENT`
- Repayment (recovery): `debtor.fund → creditor.fund` — type: `LOAN_REPAYMENT`

Tasks:
- [ ] Verify issuance transaction created correctly (creditor → debtor)
- [ ] Verify repayment view creates transaction in correct direction: `destination.fund → source.fund`
- [ ] Verify `amount_remaining_to_repay` property works: `issuance_amount - sum(repayments)`
- [ ] Reversal: only issuance is implicitly reversed; repayments must be cleared manually first
- [ ] UI: create form works; detail shows outstanding balance and "Record Repayment" button
- [ ] UI: repayment button shows remaining balance, blocks over-repayment

---

### Feature 1.12 — Purchase Operation
**Type:** Payable (`can_pay=True`, `is_partially_payable=True`, has invoice)
**Transaction flow:**
- Issuance: records liability — type: `PURCHASE_ISSUANCE` (no cash movement yet)
- Payment: `project.fund → vendor.fund` — type: `PURCHASE_PAYMENT`

Tasks:
- [ ] Verify issuance transaction is created on save (records the purchase obligation)
- [ ] Fix payment view direction: `source=operation.source.fund` (project), `target=operation.destination.fund` (vendor) — see Feature 1.3
- [ ] Verify partial payments are allowed (multiple payments up to total amount)
- [ ] UI: create form — source=Project, destination=Vendor, optional invoice formset
- [ ] UI: detail shows total amount, paid so far, remaining; "Record Payment" button
- [ ] Reversal: reverses the issuance and all payment transactions

---

### Feature 1.13 — Sale Operation
**Type:** Payable (`can_pay=True`, `is_partially_payable=True`, has invoice)
**Transaction flow:**
- Issuance: records receivable — type: `SALE_ISSUANCE` (no cash movement yet)
- Collection (payment): `client.fund → project.fund` — type: `SALE_COLLECTION`

Tasks:
- [ ] Verify issuance transaction created on save
- [ ] Fix payment view direction: `source=operation.source.fund` (client), `target=operation.destination.fund` (project) — see Feature 1.3
- [ ] Verify partial collections are allowed
- [ ] UI: create form — source=Client, destination=Project, optional invoice formset
- [ ] UI: detail shows total amount, collected so far, remaining; "Record Collection" button
- [ ] Reversal: reverses issuance and all collection transactions

---

### Feature 1.14 — Expense Operation
**Type:** Payable (`can_pay=True`, `is_partially_payable=True`, category required)
**Transaction flow:**
- Issuance: records expense obligation — type: `EXPENSE_ISSUANCE`
- Payment: `project.fund → world.fund` — type: `EXPENSE_PAYMENT`

Tasks:
- [ ] Verify issuance transaction created on save
- [ ] Fix payment view direction: `source=operation.source.fund` (project), `target=operation.destination.fund` (world) — see Feature 1.3
- [ ] Verify category is required and saved correctly
- [ ] UI: create form — source=Project, destination=World, category dropdown (required)
- [ ] UI: detail shows category, amount paid, remaining; "Record Payment" button
- [ ] Reversal: reverses issuance and all payment transactions

---

### Feature 1.15 — Capital Gain Operation
**Type:** One-shot
**Transaction flow:**
- Issuance: `system.fund → entity.fund` — type: `CAPITAL_GAIN_ISSUANCE`
- Payment: `system.fund → entity.fund` — type: `CAPITAL_GAIN_PAYMENT`

Tasks:
- [ ] Verify issuance transaction created with correct direction (system → entity)
- [ ] Verify source is the System entity (`is_system=True`)
- [ ] Verify reversal: `entity.fund → system.fund`
- [ ] UI: create form — source locked to System entity
- [ ] UI: operation detail shows issuance transaction and reversal button

---

### Feature 1.16 — Capital Loss Operation
**Type:** One-shot
**Transaction flow:**
- Issuance: `entity.fund → system.fund` — type: `CAPITAL_LOSS_ISSUANCE`
- Payment: `entity.fund → system.fund` — type: `CAPITAL_LOSS_PAYMENT`

Tasks:
- [ ] Verify issuance transaction created with correct direction (entity → system)
- [ ] Verify destination is the System entity (`is_system=True`)
- [ ] Verify reversal: `system.fund → entity.fund`
- [ ] UI: create form — destination locked to System entity
- [ ] UI: operation detail shows issuance transaction and reversal button

---

### Feature 1.17 — Worker Advance Operation
**Type:** One-shot issuance + has repayment
**Transaction flow:**
- Issuance: `project.fund → worker.fund` — type: `WORKER_ADVANCE_ISSUANCE`
- Payment: `project.fund → worker.fund` — type: `WORKER_ADVANCE_PAYMENT`
- Repayment (recovery): `worker.fund → project.fund` — type: `WORKER_ADVANCE_REPAYMENT`

Tasks:
- [ ] Verify issuance transaction created correctly (project → worker)
- [ ] Verify repayment view creates transaction: `destination.fund → source.fund` (worker → project)
- [ ] Verify `amount_remaining_to_repay` property works: `issuance_amount - sum(repayments)`
- [ ] Verify destination is an active Stakeholder in the source project
- [ ] UI: create form — source=Project, destination filtered to active workers of that project
- [ ] UI: detail shows advance amount, repaid so far, outstanding; "Record Repayment" button
- [ ] UI: repayment button blocks over-repayment (cannot repay more than advanced)

---

## EPIC 2 — Operation Bugs & Missing Flows

### Feature 2.1 — Fix AppConfig Names
**Goal:** Apps won't load correctly due to wrong `AppConfig.name` values.

Tasks:
- [*] Fix `apps/app_adjustment/apps.py`: change `name = "app_adjustment"` → `name = "apps.app_adjustment"`
- [*] Fix `apps/app_evaluation/apps.py`: same pattern
- [ ] Verify all other `apps.py` files follow the `apps.<app_name>` convention
- [ ] Run `python manage.py check` — should report 0 errors

### Feature 2.2 — Reversal Alert Template Bug
**Goal:** `reversal_alert.html` has two conditions both checking `operation.is_reversed`. Second should be `is_reversal`.

Tasks:
- [ ] Fix line 12 in `reversal_alert.html`: `elif operation.is_reversed` → `elif operation.is_reversal`
- [ ] Manually test: open a reversed operation and a reversal operation — both should show the correct badge

### Feature 2.3 — Worker Advance Repayment Flow
**Goal:** `WorkerAdvanceOperation` declares `_repayment_transaction_type` but the repayment recording view doesn't handle it yet. The advance repayment button shows in the UI but likely fails.

Tasks:
- [ ] Trace `record_transaction.py` view — confirm it handles `WORKER_ADVANCE_REPAYMENT` type
- [ ] If missing: add a branch in `record_transaction.py` for repayment transaction creation
- [ ] Test: create a worker advance → record a repayment → balance should decrease

### Feature 2.4 — Operation List Entity Typo
**Goal:** `entity_detail.html` has `entity.perosn` (typo) causing silent template errors.

Tasks:
- [*] Fix `entity.perosn` → `entity.person` in `entity_detail.html`
- [*] Search the entire templates directory for other typos: `grep -r "perosn\|entiy\|opertion" templates/`

---

## EPIC 3 — Inventory & Invoice System
> `app_invoice` references `app_inventory.InventoryItem` which doesn't exist yet. This whole epic is new.

### Feature 3.1 — Inventory App Scaffold
**Goal:** Create `apps/app_inventory/` with the `InventoryItem` model that `Invoice` depends on.

Tasks:
- [ ] Create `apps/app_inventory/` with standard Django app structure
- [ ] Add `InventoryItem` model with fields: `name`, `unit` (kg/l/piece/etc.), `description`, `is_active`
- [ ] Add `apps.app_inventory` to `INSTALLED_APPS` in `settings.py`
- [ ] Create and run migrations
- [ ] Register in admin

### Feature 3.2 — Fix Invoice Model Imports
**Goal:** `app_invoice/models.py` imports from `app_base` without the `apps.` prefix, and references `Operation` directly instead of via `app_operation`.

Tasks:
- [ ] Fix `from app_base.models import BaseModel` → `from apps.app_base.models import BaseModel`
- [ ] Fix `models.ForeignKey("Operation", ...)` → `models.ForeignKey("app_operation.Operation", ...)`
- [ ] Run `python manage.py check` — should pass

### Feature 3.3 — Invoice Total Price
**Goal:** `Invoice.total_price` raises `NotImplementedError`. Implement it.

Tasks:
- [ ] Implement `Invoice.total_price` as sum of all `InvoiceItem.total_price` values
- [ ] Add `Invoice.item_count` property
- [ ] Add validation: invoice must have at least one item before it can be saved (or warn in template)
- [ ] Write unit test

### Feature 3.4 — Invoice UI on Operation Detail
**Goal:** Purchase and Sale operations show an `invoice_formset` snippet in the create form, but there's no detail view for viewing/editing an invoice after creation.

Tasks:
- [ ] Add `invoice_detail` URL and view (read-only first)
- [ ] Link to it from `operation_detail.html`
- [ ] Show: all line items, quantities, unit prices, total

---

## EPIC 4 — Evaluation System
> `app_evaluation` has a `ProductEvaluation` model referencing `Product` which doesn't exist.

### Feature 4.1 — Product Model
**Goal:** `ProductEvaluation` has a FK to `"Product"` that doesn't exist.

Tasks:
- [ ] Decide: does `Product` live in `app_inventory` (likely yes — it's a sellable/purchasable item)?
- [ ] Add `Product` model to `app_inventory` with fields: `name`, `category`, `default_unit`, `description`
- [ ] Update `ProductEvaluation.product` FK to point to `app_inventory.Product`
- [ ] Create and run migrations

### Feature 4.2 — Evaluation Flow
**Goal:** Evaluations record the assessed price of a product at a point in time. Wire it up.

Tasks:
- [ ] Add `evaluated_at` DateField to `ProductEvaluation`
- [ ] Add a view to create an evaluation for a product
- [ ] Show evaluation history on product detail page (latest first)
- [ ] The latest evaluation's price should be usable as `InvoiceItem.unit_price` default

---

## EPIC 5 — Entity & Stakeholder Management

### Feature 5.1 — Entity List Filtering
**Goal:** The entity list shows all entities, but users need to filter by type (person / project / vendor / client / worker).

Tasks:
- [ ] Add query param filtering in `entity_list.py` view: `?type=person`, `?type=project`, etc.
- [ ] Update `entity_list.html` filter buttons to pass the correct param
- [ ] Ensure the active filter is visually highlighted

### Feature 5.2 — Stakeholder Active/Inactive Toggle
**Goal:** Stakeholders have an `active` field but there's no UI to deactivate one.

Tasks:
- [ ] Add a toggle-active view for stakeholders
- [ ] Show active/inactive status on stakeholder list in entity detail
- [ ] Inactive workers should not appear in the WorkerAdvance destination dropdown

### Feature 5.3 — Contact Info Completeness
**Goal:** Contact info forms exist but the display in entity detail may be incomplete.

Tasks:
- [ ] Audit `entity_detail.html` — confirm contact info tab renders all `ContactInfo` types (phone, email, address, website)
- [ ] Add primary contact highlight (bold/badge for `is_primary=True`)
- [ ] Add "set as primary" action

---

## EPIC 6 — Financial Categories

### Feature 6.1 — Bulk Category Creation
**Goal:** `category_bilk_create.py` (note: typo in filename) exists but likely has issues.

Tasks:
- [ ] Rename `category_bilk_create.py` → `category_bulk_create.py` and update imports in `__init__.py`
- [ ] Test the bulk create flow end-to-end: submit the form → categories appear in list
- [ ] Seed the default categories from `category.py`'s `default_categories` dict via a management command

### Feature 6.2 — Category Budget Enforcement
**Goal:** `FinancialCategory.max_limit` exists but is never enforced anywhere.

Tasks:
- [ ] Add a method `category.total_spent()` that sums all paid operation amounts in that category
- [ ] Add a method `category.remaining_budget()`
- [ ] Show remaining budget on `category_detail.html`
- [ ] Warn (but don't block) when an operation would exceed the category limit

---

## EPIC 7 — Reporting & Dashboards *(future)*

These are not started. Listed here so they are not forgotten.

- [ ] **Fund Summary Dashboard** — balances of all internal entity funds side by side
- [ ] **Project P&L Report** — for a given project: total funded, total expenses, total sales, net
- [ ] **Cash Flow Statement** — all transactions in a date range, grouped by type
- [ ] **Shareholder Equity Report** — injections minus withdrawals minus profit distributions per person
- [ ] **Financial Period Close** — lock all transactions before a given date (referenced in `TODO` comments across the codebase)

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