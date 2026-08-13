# Manual Test Plan — Farm App

> Purpose: manually exercise the main functionalities of the Farm Django app and record the outcome of each test.
> How to fill results: for each row, put the **Actual Result**, mark **Status** as `✅ Pass` / `❌ Fail` / `⚠️ Blocked`, and add any **Notes** (error message, screenshot path, bug reference, observed value). Also add a row in the Test Log at the end for every test run.
>
> Companion results spreadsheet: `manual-test-results.csv` (same test IDs — open in Excel / LibreOffice to fill in).

---

## 1. Environment & Setup

### 1.1 Prerequisites
- Python 3 with virtualenv, Django deps in `requirements.txt`.
- A local database (default SQLite via `farm/settings.py`).

### 1.2 One-time setup (development)
```bash
cd /mnt/Main/Others/Programming/django_apps/farm

# 1) Activate the virtual environment (if it exists)
source .venv/bin/activate

# 2) Install dependencies
pip install -r requirements.txt

# 3) Apply migrations
python manage.py migrate

# 4) Seed initial data (users, entities, product templates, categories)
python manage.py seed

# 5) Run the development server
python manage.py runserver
```

### 1.3 Test credentials (created by `seed`)
| User | Password | Role |
|------|----------|------|
| `admin` | `admin` | Superuser |
| `officer` | `123456` | Staff user |

### 1.4 Key URLs
- App root: `http://127.0.0.1:8000/` (redirects to entity list)
- English: `http://127.0.0.1:8000/en/` — Arabic: `http://127.0.0.1:8000/ar/`
- Login: `/login/` · Profile: `/auth/profile/` · Admin: `/admin/`
- Entities: `/entities/` · Operations: `/entities/operations/` · Inventory: `/inventory/` · Transactions: `/transactions/`

> Tip: URLs contain `<pk>` values. When a test needs an ID, open the relevant list page first and use a real ID from your data.

---

## 2. Test Environment Record (fill once per run)

| Field | Value |
|-------|-------|
| Tester name | |
| Test date | |
| OS / Browser / Version | |
| App version / git commit | |
| DB state (seeded / fresh / migrated) | |
| Server URL | |
| Language under test | |

---

## 3. Test Cases

Legend for **Status**: `✅ Pass` · `❌ Fail` · `⚠️ Blocked` (reason in Notes).

---

### 3.1 Authentication & Profile — `AUTH`

| ID | Steps | Expected Result | Actual Result | Status | Notes |
|----|-------|-----------------|---------------|--------|-------|
| AUTH-01 | Open `/login/` while logged out; submit `admin` / `admin` | Login form loads; valid credentials log you in and redirect to Profile (`LOGIN_REDIRECT_URL`) | | | |
| AUTH-02 | On `/login/`, submit wrong password | Error message shown ("Please enter a correct username and password"); stays on login page | | | |
| AUTH-03 | While logged in, open `/logout/` | You are logged out and redirected to the login page | | | |
| AUTH-04 | Logged out, try opening a protected page (e.g. `/entities/`) | Redirected to `/login/?next=...`; after login you return to the original page | | | |
| AUTH-05 | Open `/auth/profile/`; change first/last name and email; save | Profile page loads with the form pre-filled; save shows a success message and the values are updated | | | |

---

### 3.2 Entities — `ENT`

| ID | Steps | Expected Result | Actual Result | Status | Notes |
|----|-------|-----------------|---------------|--------|-------|
| ENT-01 | Open `/entities/` | Entity list loads: search box, type/deletion/activation filters, table with Entity Name / Identity Type / Roles / Fund Status / Internal | | | |
| ENT-02 | Type a search term in the search box and submit | List is filtered to matching entities | | | |
| ENT-03 | Apply filter `Type = People` / `Projects` / `System & World` | List shows only the matching entity type | | | |
| ENT-04 | Apply filter `Activation = Active Only` / `Inactive Only` | List shows only active / inactive entities | | | |
| ENT-05 | Apply filter `Deletion = Deleted Only` | List shows only soft-deleted entities (if any exist) | | | |
| ENT-06 | "Create New → Person" (`/entities/person/add/`); fill and save | Person created; appears in the entity list; detail page loads | | | |
| ENT-07 | Open `/entities/person/edit/<pk>/` for a person; change a field; save | Person updated successfully | | | |
| ENT-08 | "Create New → Project" (`/entities/project/setup/`) — Step 1: enter project basic info; continue | Project created/advanced to setup step 2 (categories) | | | |
| ENT-09 | Step through Project Setup: step 2 (categories), step 3 (product templates), step 4 (workers), step 5 (vendors), step 6 (shareholders); complete wizard | Each step saves data; project finishes setup and links categories/templates/stakeholders | | | |
| ENT-10 | Open `/entities/<pk>/` for a project | Detail shows name, ID, Active/Internal badges, **Current Fund Balance**, Contact Information, and warnings if no templates/categories are configured | | | |
| ENT-11 | Add contact via `/entities/<id>/contact/add/`; then edit via `/entities/contact/<pk>/edit/` | Contact (phone/email/address) saved and editable; PRIMARY flag displayed | | | |
| ENT-12 | On a project: add a vendor (`/entities/project/<pk>/add-vendor/`), a client, a worker, a shareholder | Each stakeholder is created and linked to the project | | | |
| ENT-13 | Edit a stakeholder via `/entities/stakeholder/<pk>/edit/` | Stakeholder record updates | | | |
| ENT-14 | Open category relation edit `/entities/category/edit/<pk>`, detail `/entities/category/detail/<pk>`, and bulk-assign `/entities/<parent_entity_id>/category/bulk-assign/` | Category relation pages load; bulk-assign associates multiple categories to the parent entity | | | |
| ENT-15 | Open `/entities/project/edit/<pk>` for a project; change a field; save | Project updated | | | |

---

### 3.3 Operations (create / list / detail) — `OPR`

> The "New Operation" dropdown on an operation list only shows operations allowed for that entity's role (shareholder vs project). Create the matching entity type first when testing.

| ID | Steps | Expected Result | Actual Result | Status | Notes |
|----|-------|-----------------|---------------|--------|-------|
| OPR-01 | Open `/entities/operations/<person_pk>/list/` for a shareholder and a project | Operation history table loads with "New Operation" dropdown; Column Legend (P = Paid, R = Remaining) and column toggle work | | | |
| OPR-02 | For a **shareholder**, create a **Cash Injection** (`<pk>/cash-injection/create`); submit amount | Operation created; fund balance increases; a Transaction is recorded | | | |
| OPR-03 | Create a **Cash Withdrawal** (`<pk>/cash-withdrawal/create`) | Operation created; fund balance decreases; Transaction recorded | | | |
| OPR-04 | Create a **Project Funding** (`<pk>/project-funding/create`) | Operation created; money moves shareholder → project | | | |
| OPR-05 | Create a **Project Re-Funding / Refund** (`<pk>/project-refunding/create`) | Operation created; money moves project → shareholder | | | |
| OPR-07 | Create a **Loan** (`<pk>/loan/create`) | Operation created; loan transaction/repayment tracking appears | | | |
| OPR-08 | Create an **Internal Transfer** (`<pk>/internal-transfer/create`) | Operation created; amount moves between internal funds | | | |
| OPR-09 | For a **project**, create an **Expense** (`<pk>/expense/create`) | Operation created; expense issuance/payment transactions recorded | | | |
| OPR-10 | For a **project**, create a **Worker Advance** (`<pk>/worker-advance/create`) | Operation created; advance tracked | | | |
| OPR-11 | For a **project**, create a **Sale** via `operation_create_view` (`<pk>/sale/create`) | Operation created; sale issuance + inventory movement recorded (stock decreases) | | | |
| OPR-12 | Open `/entities/operations/<pk>/detail/` for an existing operation | Detail shows summary, invoice items, payment transactions, inventory movement status, and reversal alert (if reversed) | | | |
| OPR-13 | Record a **Birth** (`<pk>/birth/create`) for a project with animal templates | Operation created; new animal product added; inventory/ledger updated | | | |
| OPR-14 | Record a **Death** (`<pk>/death/create`) | Operation created; product removed from stock; death movement recorded | | | |
| OPR-15 | Create an **Evaluation** (`<pk>/evaluate/<product_pk>/`) | Evaluation operation created for the product | | | |
| OPR-16 | Record a **Payment** (`/entities/operations/payment/<pk>/create`) for a purchase/loan | Payment transaction recorded; remaining balance updates | | | |
| OPR-17 | Record a **Repayment** (`/entities/operations/repayment/<pk>/create`) | Repayment transaction recorded; loan/advance balance updates | | | |
| OPR-18 | Open `/entities/operations/<pk>/invoice-items/` | Invoice items list loads with totals | | | |

---

### 3.4 Purchase Wizard — `PUR`

| ID | Steps | Expected Result | Actual Result | Status | Notes |
|----|-------|-----------------|---------------|--------|-------|
| PUR-01 | For a project open `/entities/operations/<pk>/purchase/wizard/` (step 1) | Step 1 (basic info) form loads; vendor options available | | | |
| PUR-02 | Complete step 1 → step 2; add several invoice items (formset) | Items can be added; step 2 total is computed and shown | | | |
| PUR-03 | Continue to step 3 (payment) | Optional payment sub-form loads | | | |
| PUR-04 | Continue to step 4 (goods receipt / movement) | Optional inventory movement form loads | | | |
| PUR-05 | Complete all steps and submit | Purchase **Operation** created with invoice items; **Products** created; **issuance + movement ledger entries** recorded; fund balance/stock reflect purchase | | | |
| PUR-06 | Open `/entities/operations/<pk>/purchase/invoice/` | Invoice page loads with items and totals | | | |
| PUR-07 | Use `/purchase/invoice/select-template/`, `/purchase/invoice/add-item/`, edit an item (`add-item/<idx>/`), delete an item (`delete-item/<idx>/`), then `/purchase/invoice/submit/` | Each invoice action works; totals update; submit persists the purchase | | | |
| PUR-08 | Start a purchase, then open `/purchase/wizard/cancel/` | Wizard session is cleared; redirected safely | | | |
| PUR-09 | After a purchase, verify stock on `/inventory/entity/<entity_pk>/stock/` | Stock quantity/value increased by purchased items | | | |

---

### 3.5 Sale Wizard — `SAL`

| ID | Steps | Expected Result | Actual Result | Status | Notes |
|----|-------|-----------------|---------------|--------|-------|
| SAL-01 | For a project open `/entities/operations/<pk>/sale/wizard/` (step 1) | Step 1 loads; client options available | | | |
| SAL-02 | Step 2: add invoice items | Items added; total computed | | | |
| SAL-03 | Step 3: optional payment | Payment sub-form loads | | | |
| SAL-04 | Submit the wizard | Sale **Operation** created with invoice items; **stock decreases**; issuance + movement ledger entries recorded; collection transaction recorded | | | |
| SAL-05 | Start a sale then `/sale/wizard/cancel/` | Wizard session cleared | | | |
| SAL-06 | Use `/sale/invoice/`, `/sale/invoice/select-template/`, add/edit/delete item, `/sale/invoice/submit/` | Invoice actions work; totals update; submit persists the sale | | | |

---

### 3.6 Inventory & Stock — `INV`

| ID | Steps | Expected Result | Actual Result | Status | Notes |
|----|-------|-----------------|---------------|--------|-------|
| INV-01 | Open `/inventory/entity/<entity_pk>/stock/` for a project | Current stock table + ledger history load; quantities/values consistent with operations | | | |
| INV-02 | Open `/inventory/products/<pk>/` for a product | Product detail shows ledger entries and point-in-time state | | | |
| INV-03 | Open `/inventory/entity/<entity_pk>/product-templates/` | List of product templates linked to the entity loads | | | |
| INV-04 | Open `/inventory/entity/<entity_pk>/product-templates/manage/` | Template setup/toggle page loads and changes persist | | | |
| INV-05 | Open `/inventory/product-templates/create/`; fill and save | New product template created | | | |
| INV-06 | Open `/inventory/product-templates/<pk>/` | Template detail loads (nature, unit, tracking mode, produces, gives_birth_to) | | | |
| INV-07 | From stock page use `/inventory/entity/<entity_pk>/stock/consume/` (quick consume) | Consumption movement recorded; stock decreases | | | |
| INV-08 | Create a movement via `/inventory/operations/<operation_pk>/movement/create/` | InventoryMovementLine created and ledger entry written | | | |
| INV-09 | Reverse a single movement line `/inventory/movement-lines/<pk>/reverse/` | Movement line reversed; reversal ledger entry created; stock restored | | | |
| INV-10 | Reverse a batch via `/inventory/movement-lines/batch-reverse/<group_key>/` | All lines sharing the group reversed | | | |
| INV-11 | Register deferred movements via `/inventory/operations/<operation_pk>/movement/deferred/` | Deferred movements registered and reflected in stock | | | |

---

### 3.7 Adjustments — `ADJ`

| ID | Steps | Expected Result | Actual Result | Status | Notes |
|----|-------|-----------------|---------------|--------|-------|
| ADJ-01 | On an operation open `/entities/operations/<pk>/adjustment-create` | Accounting adjustment form loads; save creates an Adjustment + transaction effect | | | |
| ADJ-02 | Open `/entities/operations/<pk>/adjustment/items/create`; add item-level delta lines | InvoiceItemAdjustment created with lines; net delta computed; Adjustment auto-created; ledger corrected | | | |
| ADJ-03 | Open `/entities/operations/<pk>/adjustments/` | Adjustments list for the operation loads | | | |
| ADJ-04 | Reverse an adjustment `/entities/operations/adjustment/<adjustment_id>/reverse/` | Adjustment reversed; its effects neutralized; reversal recorded | | | |
| ADJ-05 | Reverse an item adjustment `/entities/operations/adjustment/item/<item_adjustment_id>/reverse/` | Item adjustment reversed; lines/ledger neutralized | | | |

---

### 3.8 Financial Periods — `PRD`

| ID | Steps | Expected Result | Actual Result | Status | Notes |
|----|-------|-----------------|---------------|--------|-------|
| PRD-01 | Open `/entities/operations/periods/<entity_pk>/` | Period list loads (an initial open period should exist for the entity) | | | |
| PRD-02 | Open `/entities/operations/periods/<period_pk>/detail/` | Period detail loads with period data/status | | | |
| PRD-03 | Open `/entities/operations/periods/<period_pk>/close/`; confirm close | Period is closed; subsequent operations must belong to a new period | | | |
| PRD-04 | Open `/entities/operations/periods/<period_pk>/ledger/` | Ledger view for the period loads | | | |

---

### 3.9 Transactions — `TRX`

| ID | Steps | Expected Result | Actual Result | Status | Notes |
|----|-------|-----------------|---------------|--------|-------|
| TRX-01 | Open `/transactions/<pk>/reverse/` for a transaction; provide reason; confirm | Mirror reversal transaction created (source/target swapped); original marked as reversed | | | |
| TRX-02 | Attempt to reverse the same transaction again | Validation error — cannot reverse twice; original's `reversed_by` already set | | | |
| TRX-03 | Attempt to reverse a transaction that is itself a reversal | Validation error — cannot reverse a reversal | | | |

---

### 3.10 General / Cross-cutting — `GEN`

| ID | Steps | Expected Result | Actual Result | Status | Notes |
|----|-------|-----------------|---------------|--------|-------|
| GEN-01 | Open `/` while logged in | Redirected to `/entities/` (entity list) | | | |
| GEN-02 | Switch language via the language switcher (EN ↔ AR) | UI strings translate (translated strings in English/Arabic; untranslated ones stay as-is) | | | |
| GEN-03 | Visit a non-existent URL (e.g. `/entities/999999/`) | Custom 404 page shows | | | |
| GEN-04 | Open `/admin/` as `admin` | Django admin loads and is usable | | | |
| GEN-05 | Trigger a server error path if feasible | Custom 500 page shows (in production-like settings) | | | |

---

## 4. Test Log (one row per run)

| Run # | Date | Tester | Environment | Total | Pass | Fail | Blocked | Open Bugs | Sign-off |
|-------|------|--------|-------------|-------|------|------|---------|-----------|----------|
| 1 | | | | | | | | | |
| 2 | | | | | | | | | |

---

## 5. Bug Report Template (copy per failure)

```
BUG-<NNN>: <short title>
---------------------------------------------
Module / Test ID : (e.g. OPR-02)
Severity        : Critical / Major / Minor / Cosmetic
Steps to reproduce:
  1. ...
  2. ...
Expected         : ...
Actual           : ...
Environment      : (browser/OS, seeded or fresh DB)
Screenshot/log   : <path>
```
