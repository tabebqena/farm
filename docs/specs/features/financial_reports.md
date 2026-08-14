# Financial Reports — Reporting Contract

**Epic:** 7 — Reporting & Dashboards (`docs/specs/README.md` → `epic_7_reporting`)
**Type:** Read-only aggregation — no writes
**Actions:** `view`, `scope-by-entity`, `scope-by-period`, `scope-by-date` (no `create` / `reverse` / `pay`)
**Contract status:** v1 (mapped) — report formulas registered against implementing properties/views, per-entity-type applicability recorded, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Financial Reports** feature.
> Every clause below names its implementing code (model → derived property → stock → transaction type → view → template) and its pinning test — as plain names, never links, so renames do not break the spec.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> This feature spec follows the shared structure of `_OPERATION_SPEC_TEMPLATE.md` where it applies, adapted from a mutating operation to a **read-only** reporting domain (the "actions" are queries, not writes).

---

## 1. Identity — report catalog

The reporting surface exposes **four accounting statements** plus **operational summary views**. Every report is a *derived, read-only* calculation over `Transaction`, `InventoryMovementLine`, and `FinancialPeriod` data — nothing here writes.

| # | Report | Type | Scope | As-of semantics | Primary implementation |
|---|--------|------|-------|-----------------|------------------------|
| R1 | Fund Balance | point-in-time | person + project | as of `dt` | `Entity.balance_at` |
| R2 | Payables | point-in-time | person + project | as of `dt` | `Entity.payables_at` |
| R3 | Receivables | point-in-time | person + project | as of `dt` | `Entity.receivables_at` |
| R4 | Inventory Value | point-in-time | project only | as of `dt` | `stock.inventory_value` |
| R5 | Income Statement (P&L) | period | project only | `[start, end)` | `Entity.profit_loss` |
| R6 | Balance Sheet | period-end snapshot | project only | `end_date` | `FinancialPeriod.end_assets` / `end_liabilities` / equity |
| R7 | Cash Flow Statement | period | person + project | `[start, end)` | `FinancialPeriod.cash_in` / `cash_out` / `previous_balance` / `end_balance` |
| R8 | Statement of Changes in Equity | period | person + project | `[start, end)` | derived — see §3.6 (not yet a dedicated page) |

**Configuration / currency:**
- Currency symbol: `settings.CURRENCY_SYMBOL` (default `"$"`) — every amount renders with this symbol.
- Amounts are `Decimal`, rendered with two decimals (`floatformat:2`).
- Virtual entities (world / system) have **no reports** — they are bookkeeping counters, not reportable subjects.

---

## 2. Registered business logic (contract map)

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Entity types (person / project / system / world) | `EntityType` + `Entity` in `apps/app_entity/models/__init__.py` |
| Derived balance / obligation / P&L properties | `Entity.balance_at`, `payables_at`, `receivables_at`, `profit_loss` — same file |
| Accounting periods | `FinancialPeriod` in `apps/app_operation/models/period.py` |
| Transaction ledger row | `Transaction` in `apps/app_transaction/models.py` |
| Transaction-type classification | `TransactionType` in `apps/app_transaction/transaction_type.py` |
| Movement-based stock valuation | `stock.inventory_value` / `movement_state` / `valuation_unit_cost` in `apps/app_inventory/stock.py` |

### 2.2 Report metrics (derived properties)

| Report / metric | Implementing code |
|-----------------|-------------------|
| Fund balance at a date | `Entity.balance_at` → `Entity._tx_sum` (payment types only) |
| Payables / receivables | `Entity.payables_at` / `receivables_at` → `Entity._tx_sum_excluding_reversed` |
| P&L for a period | `Entity.profit_loss` → `_signed_sum` (reversal-negated) |
| Period cash in / out | `FinancialPeriod.cash_in` / `cash_out` |
| Period opening / closing balance | `FinancialPeriod.previous_balance` / `balance` / `end_balance` |
| Period inventory flows | `FinancialPeriod.inventory_value_previous` / `inventory_value_in` / `inventory_value_out` / `inventory_value` / `inventory_value_end` |
| Period payables / receivables flows | `FinancialPeriod.payables_previous` / `payables_in` / `payables_out` / `payables_end`; `receivables_previous` / `receivables_in` / `receivables_out` / `receivables_end` |
| Outstanding loans / advances | `FinancialPeriod.outstanding_loan_credited` / `outstanding_loan_received` / `outstanding_worker_advance_paid` / `outstanding_worker_advance_received` |
| Balance-sheet snapshot | `FinancialPeriod.end_assets` / `end_liabilities` (equity = residual, §3.4) |
| Period profit / loss | `FinancialPeriod.amount` → `Entity.profit_loss(period)` |
| Period open / closed / profit / loss flags | `FinancialPeriod.is_closed`, `can_close`, `is_profit`, `is_loss`, `as_of` |

### 2.3 Transaction-type classification layer

| Concern | Implementing code |
|---------|-------------------|
| Types that move cash (affect balance) | `TransactionType.payment_types()` |
| Types that record obligations/receivables (no cash) | `TransactionType.issuance_types()` |
| Adjustment increase / decrease pairs | `PURCHASE/SALE/EXPENSE_ADJUSTMENT_INCREASE/DECREASE` |
| Reversal linkage | `Transaction.reversal_of` / `reversed_by` |

### 2.4 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Entity detail — balance + financial summary card | `entity_detail_view` + `app_entity/entity_detail.html` |
| Period list — balance / receivables / payables / inventory / P/L columns | `period_list_view` + `app_operation/period_list.html` |
| Period detail — cash, payables, receivables, inventory cards + period summary | `period_detail_view` + `app_operation/period_detail.html` |
| Payment-transactions page (running balance) | `entity_payment_transactions_view` + `app_transaction/entity_payment_transactions.html` |
| Payables page (running obligation) | `entity_payables_view` + `app_transaction/entity_payables.html` |
| Receivables page (running obligation) | `entity_receivables_view` + `app_transaction/entity_receivables.html` |
| Stock detail (project only) | `stock_detail` view + template |
| URL wiring | `apps/app_transaction/urls.py`, `apps/app_operation/urls.py`, `apps/app_inventory/urls.py` |
| Navigation entries | `apps/app_base/navigation.py` |

### 2.5 Tests

| Concern | Test file |
|---------|-----------|
| Entity detail financial-summary context | `apps/app_entity/tests/test_views_get_entity_detail_view.py` |
| Payment transactions / payables / receivables pages | `apps/app_transaction/tests.py` (`EntityTransactionsViewTests`, `EntityPayablesViewTests`, `EntityReceivablesViewTests`) |
| Period model metrics (balance, inventory, end_assets, end_liabilities) | `apps/app_operation/tests/period/test_period_model.py` |
| Stock valuation | `apps/app_inventory/tests/test_stock.py` |

---

## 3. Report definitions & formulas

### 3.0 Common building blocks (how every amount is derived from the models)

Every cash amount is an **aggregation over `Transaction` rows**; every stock amount is an **aggregation over `InventoryMovementLine` / `Product` / `ProductCapitalValuation` rows**. The shared rules:

- **Cash rows** = `Transaction` with `deleted_at IS NULL` and `type` in the report's type set. The ledger has no balance column — balance is always `SUM(amount)` grouped by direction.
- **Direction** is decided by which foreign key points at the reporting entity: `source = entity` means the entity gives the amount (outgoing), `target = entity` means the entity receives it (incoming).
- **`Transaction.type`** is the only discriminator between cash movement, obligations, and value bookkeeping. The sets come from `TransactionType.payment_types()` (cash) and `TransactionType.issuance_types()` (obligations).
- **Reversal linkage:** a reversal row carries `reversal_of → original`; the original exposes `reversed_by → reversal`. Each report decides whether to include or exclude these (see §6).
- **Stock rows:** `InventoryMovementLine` carries `product`, `quantity`, `date`, and an implicit sign from `operation.operation_type` (PURCHASE / BIRTH = inbound `+`; SALE / DEATH / CONSUMPTION = outbound `−`). Value per unit is `Product.unit_price` (the carried cost). Value-only adjustments come from `ProductCapitalValuation.amount` (signed: gain `+`, loss `−`), linked to `product` and to an `operation` that may be reversed.

---

### 3.1 R1 — Fund Balance

- **Purpose:** net cash position of an entity's fund at a point in time.
- **Scope:** person + project (world/system excluded — virtual).
- **Calculation (models):** over `Transaction` where
  - `deleted_at IS NULL`,
  - `type IN TransactionType.payment_types()`,
  - `date ≤ as_of`:
  - `incoming = SUM(amount)` where `target = entity`
  - `outgoing = SUM(amount)` where `source = entity`
  - **balance = incoming − outgoing**
- **Reversal handling:** original **and** reversal transactions are both counted (with their own sign), so a cross-period reversal lands in the correct period with the correct sign.
- **Status:** implemented — `Entity.balance_at` / `Entity.balance` (today).

---

### 3.2 R2 / R3 — Payables & Receivables

- **Purpose:** outstanding obligations owed **by** the entity (payables) and amounts owed **to** the entity (receivables), at a point in time.
- **Scope:** person + project. A person can hold both sides across roles (vendor ⇒ receivable, client ⇒ payable, lender ⇒ receivable, worker ⇒ receivable).
- **Calculation (models):** over `Transaction` where
  - `deleted_at IS NULL`,
  - `date ≤ as_of`,
  - `reversal_of IS NULL` (reversal rows are not obligations),
  - and (`reversed_by IS NULL` OR `reversed_by.date > as_of`) — an original reversed after `as_of` still counts today:
  - **payables = [Σ source-side increase − Σ source-side decrease] + [Σ target-side increase − Σ target-side decrease]** with the buckets:
    - source increase: `PURCHASE_ISSUANCE`, `PURCHASE_ADJUSTMENT_INCREASE`, `SALE_ISSUANCE`, `SALE_ADJUSTMENT_INCREASE`, `EXPENSE_ISSUANCE`, `EXPENSE_ADJUSTMENT_INCREASE`, `PROJECT_REFUND_ISSUANCE`
    - source decrease: `PURCHASE_PAYMENT`, `SALE_COLLECTION`, `EXPENSE_PAYMENT`, `WORKER_ADVANCE_REPAYMENT`, `LOAN_REPAYMENT`, `PROJECT_REFUND_PAYMENT`
    - target increase: `WORKER_ADVANCE_PAYMENT`, `LOAN_PAYMENT`
    - target decrease: `PURCHASE_ADJUSTMENT_DECREASE`, `SALE_ADJUSTMENT_DECREASE`, `EXPENSE_ADJUSTMENT_DECREASE`
  - **receivables = the mirror buckets** (the same transaction sets, with source/target and increase/decrease swapped — a receivable for one side is the counterpart of the other's payable).
- **Reversal handling:** `_tx_sum_excluding_reversed` — reversal rows excluded; originals reversed before `as_of` excluded, reversed after `as_of` still counted.
- **Status:** implemented — `Entity.payables_at` / `receivables_at` (+ drill-down pages R10/R11, §3.7).

---

### 3.3 R5 — Income Statement / P&L

- **Purpose:** summarize **revenues** and **expenses** over a period → **net profit or loss**.
- **Scope:** project **only** — `Entity.profit_loss` raises `ValueError` for non-project funds.
- **Calculation (models):** over `Transaction` where
  - `deleted_at IS NULL`,
  - `date ∈ [period.start_date, period.end_date)` (when the period is open, `date ≥ period.start_date`):
  - define `signed(amount) = amount` if `reversal_of IS NULL` else `−amount` (a reversal cancels its original in the same or later period).
  - **income =** `Σ signed(target = fund ∧ type ∈ {SALE_ISSUANCE, CORRECTION_CREDIT_ISSUANCE, PURCHASE_ISSUANCE (project as vendor), SALE_ADJUSTMENT_INCREASE, PURCHASE_ADJUSTMENT_INCREASE})` **−** `Σ signed(target = fund ∧ type ∈ {SALE_ADJUSTMENT_DECREASE, PURCHASE_ADJUSTMENT_DECREASE})`
  - **costs =** `Σ signed(source = fund ∧ type ∈ {PURCHASE_ISSUANCE, EXPENSE_ISSUANCE, CORRECTION_DEBIT_ISSUANCE, SALE_ISSUANCE (project as client), PURCHASE_ADJUSTMENT_INCREASE, SALE_ADJUSTMENT_INCREASE, EXPENSE_ADJUSTMENT_INCREASE})` **−** `Σ signed(source = fund ∧ type ∈ {PURCHASE_ADJUSTMENT_DECREASE, SALE_ADJUSTMENT_DECREASE, EXPENSE_ADJUSTMENT_DECREASE})`
  - **P&L = income − costs**
- **Deliberately excluded:** Capital Gain, Capital Loss, Consumption are **not** accounting transactions — their value effect flows through inventory value (`stock.inventory_value` / `FinancialPeriod.end_assets`), not P&L.
- **Reversal handling:** originals **and** reversals are included with the correct sign (reversals negated), so cross-period reversals land in the right period.
- **Status:** implemented — `Entity.profit_loss`; surfaced on `FinancialPeriod.amount` (closed project periods only) and period list/detail P/L columns.

---

### 3.4 R6 — Balance Sheet

- **Purpose:** financial position **at a moment in time**: Assets (what the entity owns), Liabilities (what the entity owes), Equity (ownership residual).
- **Scope:** project only (for a person the sheet collapses to: Assets = balance, Liabilities = 0, Equity = balance — see §4).
- **As-of:** `end_date` when closed; `as_of = today` while open.
- **Calculation (models)** — intended full sheet, all as-of `as_of`:
  - **Cash & fund balance** = `balance_at(as_of)` (R1).
  - **Receivables** = `receivables_at(as_of)` (R3) — this already includes trade receivables **and** loans given (`LOAN_PAYMENT` as source) **and** advances paid (`WORKER_ADVANCE_PAYMENT` as source).
  - **Inventory value** = `stock.inventory_value(entity, as_of)` = per product: net active movement quantity × `Product.unit_price` + Σ `ProductCapitalValuation.amount` (rows whose `operation.reversed_by` is null).
  - **Assets** = cash + receivables + inventory. *(Equivalently: cash + inventory + `outstanding_loan_credited` + `outstanding_worker_advance_paid` + trade receivables — do **not** add loans/advances twice.)*
  - **Payables** = `payables_at(as_of)` (R2) — already includes trade payables, loans received, and advances received.
  - **Liabilities** = payables.
  - **Equity** = Assets − Liabilities (residual) = contributed capital + cumulative retained earnings (P&L).
- **Current implementation (subset):** `FinancialPeriod.end_assets` = cash balance + inventory value + `outstanding_loan_credited` + `outstanding_worker_advance_paid` (**excludes trade receivables**); `end_liabilities` = `outstanding_loan_received` + `outstanding_worker_advance_received` (**excludes trade payables**). Trade payables/receivables are tracked separately (R2/R3) but not yet folded into the sheet. **Refinement for Epic 7:** fold `payables_at`/`receivables_at` into the sheet so Assets − Liabilities reconciles exactly to contributed capital + cumulative P&L.
- **Status:** partial — `FinancialPeriod.end_assets` / `end_liabilities` implemented and surfaced in the period detail "Period Summary"; full reconciliation is a documented gap.

---

### 3.5 R7 — Cash Flow Statement

- **Purpose:** track cash moving in and out over a period → why the balance changed.
- **Scope:** person + project.
- **Calculation (models):** over `Transaction` where `deleted_at IS NULL`, `type IN TransactionType.payment_types()`, `date ∈ [start_date, end_date)`:
  - **Opening cash** = `previous_balance` = `balance_at(start_date − 1 day)`.
  - **cash_in** = `Σ amount` where `target = entity`; **cash_out** = `Σ amount` where `source = entity`.
  - **Closing cash** = opening + cash_in − cash_out = `balance` (open) / `end_balance` (closed).
  - **Activity split (intended):**
    - *Operating* — `PURCHASE_PAYMENT`, `SALE_COLLECTION`, `EXPENSE_PAYMENT`.
    - *Financing* — `CASH_INJECTION_PAYMENT`, `CAPITAL_WITHDRAWAL_PAYMENT`, `PROJECT_FUNDING_PAYMENT`, `PROJECT_REFUND_PAYMENT`, `LOAN_PAYMENT`, `LOAN_REPAYMENT`, `WORKER_ADVANCE_PAYMENT`, `WORKER_ADVANCE_REPAYMENT`, `INTERNAL_TRANSFER_PAYMENT`, `CORRECTION_CREDIT_PAYMENT`, `CORRECTION_DEBIT_PAYMENT`.
    - *Investing* — none today (Birth / Death / Capital Gain / Capital Loss are non-cash; value flows via inventory).
- **Current implementation:** a **combined** `cash_in` / `cash_out` plus `previous_balance` / `end_balance`. The operating/investing/financing split is a **future refinement** (Epic 7).
- **Status:** partial — `FinancialPeriod.cash_in` / `cash_out` / `previous_balance` / `end_balance` implemented and shown in the period detail "Cash & Balance" card.

---

### 3.6 R8 — Statement of Changes in Equity

- **Purpose:** explain how equity moved across a period: opening equity → capital contributed → net profit/loss → withdrawals/distributions → closing equity.
- **Scope:** person + project (different drivers, §4).
- **Calculation (models):**
  - **Person** (equity = fund balance):
    - opening equity = `previous_balance`
    - contributions (incoming payment txs) = `CASH_INJECTION_PAYMENT` + `PROJECT_FUNDING_PAYMENT` (as `target`)
    - withdrawals (outgoing payment txs) = `CAPITAL_WITHDRAWAL_PAYMENT` + `PROJECT_REFUND_PAYMENT` (as `source`)
    - net change = contributions − withdrawals; closing equity = `balance` / `end_balance`.
  - **Project** (equity = contributed capital + retained earnings):
    - contributed capital = Σ incoming financing payment types (funding, injections) − Σ outgoing financing payment types (refunds, withdrawals)
    - retained earnings = cumulative `profit_loss` over closed periods
    - distributions via `DistributionPlan` / `ShareholderAllocation` (models not yet present — future)
    - closing equity = Assets − Liabilities (R6).
- **Status:** not implemented as a page. The inputs (balance, cash flows, P&L) all exist; the dedicated statement is a future Epic 7 deliverable.

---

### 3.7 Operational summary views (R9–R12)

| # | View | Calculation (models) | Implementing code |
|---|------|----------------------|-------------------|
| R9 | Payment Transactions | all `Transaction` where `(source = entity OR target = entity)`, `type IN payment_types()`, `deleted_at IS NULL`, ordered by `date, pk`; each row annotated `direction` (incoming if `target = entity` else outgoing) and a running balance (`+amount` incoming, `−amount` outgoing); totals = Σ incoming / Σ outgoing; current balance = `entity.balance` | `entity_payment_transactions_view` |
| R10 | Payables detail | the `Transaction` rows behind R2 (same filters), annotated `direction` = increase/decrease and a running obligation balance; totals = Σ increase / Σ decrease; current obligation = `entity.payables` | `entity_payables_view` |
| R11 | Receivables detail | mirror of R10 using the R3 buckets; current obligation = `entity.receivables` | `entity_receivables_view` |
| R12 | Stock value | `stock.inventory_value(entity, today)` — per `Product` owned by the entity: net active `InventoryMovementLine.quantity` × `Product.unit_price` + Σ active `ProductCapitalValuation.amount` | `stock_detail` + `stock.inventory_value` |

---

## 4. Entity-type applicability — what matters for persons vs projects

| Metric / report | Person | Project |
|-----------------|--------|---------|
| Fund balance | ✓ — the person's wallet | ✓ — project cash position |
| Cash in / out | ✓ — injections, withdrawals, funding, refunds, repayments | ✓ — full cash-flow statement (R7) |
| Payables | ✓ — as client / borrower / debtor | ✓ — purchases, expenses, loans received, advances received |
| Receivables | ✓ — as vendor / lender / worker / shareholder | ✓ — sales, loans given, advances paid |
| Inventory value | ✗ — persons hold no stock | ✓ — movement-based stock value (R4/R12) |
| Income Statement / P&L | ✗ — `profit_loss` raises for non-projects | ✓ — R5, the primary project profitability report |
| Balance Sheet | reduced — Assets = balance, Liabilities = 0, Equity = balance | ✓ — R6 full sheet (assets / liabilities / equity) |
| Statement of Changes in Equity | equity = balance (injections − withdrawals) | equity = contributed capital + retained earnings (− distributions) |
| Financial periods | ✓ — auto-created open period on activation | ✓ — sequential, closeable periods; the backbone of R5–R8 |
| Loans / worker advances | ✓ — tracked via receivables/payables buckets | ✓ — `outstanding_loan_*` / `outstanding_worker_advance_*` on periods |

**Key asymmetry (spec contract):** P&L and full balance sheet are **project-only**. A person's "financial statements" reduce to balance, cash flows, and the payables/receivables positions — the system therefore never offers R5/R6 for a person.

---

## 5. Period & as-of contract

- **Interval semantics:** `[start_date, end_date)` — start inclusive, end exclusive.
- **As-of reference:** `FinancialPeriod.as_of` = `end_date` if set, else today.
- **Opening balance:** `previous_balance` = `balance_at(start_date − 1 day)` — the beginning-of-period cash position.
- **Closed vs open:**
  - A period is `is_closed` when `end_date` is set and before today; it is `can_close` while `end_date is None`.
  - Closed project periods produce a final `amount` (= `profit_loss(period)`); open periods expose **current** (as-of-today) values.
  - `end_balance`, `inventory_value_end`, `payables_end`, `receivables_end`, `end_assets` return `None` while the period is open.
- **Period chaining:** closing an active entity's period auto-creates the next open period starting on `end_date`; closing an inactive entity returns `None`.
- **Guards:** no-overlap validation per entity; `end_date` immutable once set; closed periods reject new operations/payments/movements dated inside them (reversals exempt).

---

## 6. Reversal & transaction-type handling

| Report | Reversal policy |
|--------|-----------------|
| Fund balance (R1) | count originals + reversals (signed) — cross-period reversals land in the correct period |
| Payables / receivables (R2/R3) | `_tx_sum_excluding_reversed`: exclude reversal (mirror) rows; exclude originals reversed before `as_of`; include those reversed after `as_of` |
| P&L (R5) | `_signed_sum`: include originals + reversals, negating reversal amounts |
| Cash flow (R7) | payment types only; reversal rows count as cash movement with the original's type/amount |
| Balance sheet (R6) | built from the above per-component rules (as-of `end_date`) |
| Inventory (R4/R12) | `active_movements`: exclude reversal lines and reversed originals; `ProductCapitalValuation` rows exclude those whose `operation.reversed_by` is set |

**Non-accounting types:** `BIRTH` / `DEATH` / `CAPITAL_GAIN` / `CAPITAL_LOSS` / `CONSUMPTION` payment records never enter balance or P&L — their value is carried by movement-based inventory (`stock.inventory_value`), which feeds `end_assets`.

---

## 7. View / UI contract

| Concern | Behavior |
|---------|----------|
| Entity detail | `Current Fund Balance` card (balance + "View Payment Transactions") + `Financial Summary` card (balance → R9, payables → R10, receivables → R11, stock value → R12, projects only) |
| Period list | one row per period: balance, receivables, payables, inventory, P/L (colored +/−), plus Detail / Ledger / Close actions |
| Period detail | four cards — Cash & Balance (previous / cash in / cash out / end or current), Payables (previous / new / paid / end), Receivables (previous / new / collected / end), Inventory (previous / added / sold / end); when closed, a `Period Summary` with start/end dates, end balance, end assets, end liabilities, end inventory, profit/loss |
| Payment transactions page | summary cards (current balance, total incoming, total outgoing, count) + paginated table with direction and running balance |
| Payables / receivables pages | summary (total increase, total decrease, current obligation) + paginated running-balance table |
| Currency | `settings.CURRENCY_SYMBOL` on every page |
| Navigation | entries for payment transactions, payables, receivables, periods, stock (project) |
| Future (Epic 7) | dedicated Income Statement, Cash Flow, and Equity pages; operating/investing/financing split; full balance-sheet reconciliation |

---

## 8. Branch catalog (all possible report branches)

**Common data rules:** payment vs issuance types · reversal-aware sums · non-accounting ops excluded · virtual entities excluded · project-only guards (P&L, balance sheet, inventory) · `end_*` returns `None` while open · closed-period finalization

**R1 Fund balance:** incoming payment txs minus outgoing payment txs · original + reversal counted · `payment_types()` only

**R2/R3 Payables/receivables:** four increase/decrease buckets (source/target) · reversal rows excluded · reversed-before-`as_of` excluded, reversed-after counted

**R5 P&L:** income bucket (target=fund) vs cost bucket (source=fund) · reversal-negated signed sum · `[start, end)` date filter · non-project raises `ValueError` · capital gain/loss/consumption excluded (flow via inventory)

**R6 Balance sheet:** assets = cash + inventory + receivables (incl. loans/advances given) · liabilities = payables (incl. loans/advances received) · equity = assets − liabilities · current impl = subset (no trade payables/receivables) — documented refinement

**R7 Cash flow:** opening = `previous_balance` · in/out = payment types · closing = balance/end_balance · operating/investing/financing split future

**R8 Equity:** person = balance (injections − withdrawals) · project = contributed capital + retained earnings (− distributions, future)

**R9–R12 operational views:** running balance/obligation over all rows (correct across pages) · totals · 25-per-page pagination · 404 for missing entity · auth required

---

## 9. Test coverage matrix

| Area | Test method / class | Branch(es) |
|------|---------------------|------------|
| Entity detail financial summary context | `test_views_get_entity_detail_view.py` (context exposes payables/receivables/stock_value/currency; payables from expense issuance; stock value from a ledger/movement) | R2, R3, R4, R12 |
| Payment-transactions page | `EntityTransactionsViewTests` (payment-only filter, directions, running balance/totals, entity scoping, 404, auth redirect, pagination) | R1, R9 |
| Payables page | `EntityPayablesViewTests` (issuance ↑ / payment ↓ running balance + totals; non-payable types excluded; 404; auth; pagination) | R2, R10 |
| Receivables page | `EntityReceivablesViewTests` (advance ↑ / repayment ↓; non-receivable excluded; 404; auth; pagination) | R3, R11 |
| Period balance & inventory | `test_period_model.py` (previous/end balance, inventory_value_previous/in/out/end, end_assets/end_liabilities incl. loans & advances) | R1, R4, R6 |
| Inventory value basis | `test_stock.py` (`inventory_value`, `movement_state`, capital gain/loss in value) | R4, R12 |
| P&L reversal invariance | consumption create/reverse tests (`test_consumption_*` — consumption does not change `profit_loss`) | R5 |
| P&L period scope | `test_period_model.py` / period `amount` (closed project periods only) | R5 |
