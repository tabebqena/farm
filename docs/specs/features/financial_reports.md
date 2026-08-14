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

| # | Report | العربية | Type | Scope | As-of semantics | Primary implementation |
|---|--------|---------|------|-------|-----------------|------------------------|
| R1 | Fund Balance | رصيد الصندوق | point-in-time | person + project | as of `dt` | `Entity.balance_at` |
| R2 | Payables | الذمم الدائنة (المستحقة للغير) | point-in-time | person + project | as of `dt` | `Entity.payables_at` |
| R3 | Receivables | الذمم المدينة (المستحقة لنا) | point-in-time | person + project | as of `dt` | `Entity.receivables_at` |
| R4 | Inventory Value | قيمة المخزون | point-in-time | project only | as of `dt` | `stock.inventory_value` |
| R5 | Income Statement (P&L) | قائمة الدخل | period | project only | `[start, end)` | `Entity.profit_loss` |
| R6 | Balance Sheet | قائمة المركز المالي (الميزانية العمومية) | period-end snapshot | project only | `end_date` | `FinancialPeriod.end_assets` / `end_liabilities` / equity |
| R7 | Cash Flow Statement | قائمة التدفقات النقدية | period | person + project | `[start, end)` | `FinancialPeriod.cash_in` / `cash_out` / `previous_balance` / `end_balance` |
| R8 | Statement of Changes in Equity | قائمة التغيرات في حقوق الملكية | period | person + project | `[start, end)` | derived — see §3.6 (not yet a dedicated page) |

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

Common building blocks (how every amount is derived):

- **Payment types** (`TransactionType.payment_types()`): the only types that move a fund balance. Virtual-value ops — Birth, Death, Capital Gain, Capital Loss, Consumption — are **excluded** (their `*_PAYMENT` records are non-cash bookkeeping; value lives in inventory).
- **Issuance types** (`TransactionType.issuance_types()`): obligations / receivables, no cash movement.
- **Reversal handling** differs per report and is specified in §6.

### 3.1 R1 — Fund Balance (رصيد الصندوق)

- **Purpose:** net cash position of an entity's fund at a point in time.
- **Scope:** person + project (world/system excluded — virtual).
- **Formula:** `balance_at(dt) = Σ incoming payment txs (target=entity, date ≤ dt) − Σ outgoing payment txs (source=entity, date ≤ dt)`.
- **Reversal handling:** original **and** reversal transactions are both counted (with their sign), so a cross-period reversal lands in the correct period with the correct sign.
- **Status:** implemented — `Entity.balance_at` / `Entity.balance` (today).

### 3.2 R2 / R3 — Payables & Receivables (الذمم الدائنة / المدينة)

- **Purpose:** outstanding obligations owed **by** the entity (payables) and amounts owed **to** the entity (receivables), at a point in time.
- **Scope:** person + project. A person can hold both sides across roles (vendor ⇒ receivable, client ⇒ payable, lender ⇒ receivable, worker ⇒ receivable).
- **Payables formula** (`payables_at`): `[increase_as_source − decrease_as_source] + [increase_as_target − decrease_as_target]`, where:
  - increase_as_source: `PURCHASE_ISSUANCE`, `PURCHASE_ADJUSTMENT_INCREASE`, `SALE_ISSUANCE`, `SALE_ADJUSTMENT_INCREASE`, `EXPENSE_ISSUANCE`, `EXPENSE_ADJUSTMENT_INCREASE`, `PROJECT_REFUND_ISSUANCE`
  - decrease_as_source: `PURCHASE_PAYMENT`, `SALE_COLLECTION`, `EXPENSE_PAYMENT`, `WORKER_ADVANCE_REPAYMENT`, `LOAN_REPAYMENT`, `PROJECT_REFUND_PAYMENT`
  - increase_as_target: `WORKER_ADVANCE_PAYMENT`, `LOAN_PAYMENT`
  - decrease_as_target: `PURCHASE/SALE/EXPENSE_ADJUSTMENT_DECREASE`
- **Receivables formula** (`receivables_at`): the mirror buckets (see the model — a receivable for one side is the counterpart of the other's payable).
- **Reversal handling:** both reports use `_tx_sum_excluding_reversed` — reversal (mirror) transactions are excluded, and transactions reversed before `dt` are excluded (reversed after `dt` still count).
- **Status:** implemented — `Entity.payables_at` / `receivables_at` (+ drill-down pages R9/R10, §7).

### 3.3 R5 — Income Statement / P&L (قائمة الدخل)

- **Purpose:** summarize **revenues** and **expenses** over a period → **net profit or loss**.
- **Scope:** project **only** — `Entity.profit_loss` raises `ValueError` for non-project funds.
- **Formula:** `profit_loss(period) = income − costs`, where each bucket is a *reversal-aware signed sum* (`_signed_sum` negates any reversal transaction) of **issuance/adjustment** transactions dated `[start_date, end_date)`:
  - **Income (target = fund):** `SALE_ISSUANCE`, `CORRECTION_CREDIT_ISSUANCE`, `PURCHASE_ISSUANCE` (project acting as vendor), plus `SALE/PURCHASE_ADJUSTMENT_INCREASE`; **minus** `SALE/PURCHASE_ADJUSTMENT_DECREASE`.
  - **Costs (source = fund):** `PURCHASE_ISSUANCE`, `EXPENSE_ISSUANCE`, `CORRECTION_DEBIT_ISSUANCE`, `SALE_ISSUANCE` (project acting as client), plus `PURCHASE/SALE/EXPENSE_ADJUSTMENT_INCREASE`; **minus** the matching `_DECREASE` types.
- **Deliberately excluded:** Capital Gain, Capital Loss, Consumption are **not** accounting transactions — their value effect flows through inventory value (`stock.inventory_value` / `FinancialPeriod.end_assets`), not P&L.
- **Reversal handling:** originals **and** reversals are included with the correct sign (reversals negated), so cross-period reversals land in the right period.
- **Status:** implemented — `Entity.profit_loss`; surfaced on `FinancialPeriod.amount` (closed project periods only) and period list/detail P/L columns.

### 3.4 R6 — Balance Sheet (قائمة المركز المالي / الميزانية العمومية)

- **Purpose:** financial position **at a moment in time**: Assets (ما تملكه), Liabilities (ما تدين به), Equity (حقوق الملكية).
- **Scope:** project only (for a person the sheet collapses to: Assets = balance, Liabilities = 0, Equity = balance — see §4).
- **As-of:** `end_date` when closed; `as_of = today` while open.
- **Intended formula:**
  - **Assets (الأصول)** = cash & fund balance (`balance_at(as_of)`) + trade receivables + inventory value (`stock.inventory_value`) + loans given (`outstanding_loan_credited`) + worker advances paid (`outstanding_worker_advance_paid`). `receivables_at` already contains loans/advances given, so the asset side may equivalently be `balance + inventory + receivables_at` **without** re-adding loans/advances (no double counting).
  - **Liabilities (الالتزامات)** = trade payables + loans received (`outstanding_loan_received`) + worker advances received (`outstanding_worker_advance_received`). `payables_at` already contains loans/advances received, so this equals `payables_at(as_of)`.
  - **Equity (حقوق الملكية)** = Assets − Liabilities (residual) = contributed capital + cumulative retained earnings (P&L).
- **Current implementation (subset):** `FinancialPeriod.end_assets` = cash balance + inventory value + loans given + advances paid (**excludes trade receivables**); `end_liabilities` = loans received + advances received (**excludes trade payables**). Trade payables/receivables are tracked separately (R2/R3) but not yet folded into the sheet. **Refinement for Epic 7:** fold `payables_at`/`receivables_at` into the sheet so Assets − Liabilities reconciles exactly to contributed capital + cumulative P&L.
- **Status:** partial — `FinancialPeriod.end_assets` / `end_liabilities` implemented and surfaced in the period detail "Period Summary"; full reconciliation is a documented gap.

### 3.5 R7 — Cash Flow Statement (قائمة التدفقات النقدية)

- **Purpose:** track cash moving in and out over a period → why the balance changed.
- **Scope:** person + project.
- **Intended formula:**
  - Opening cash = `previous_balance` (= `balance_at(start_date − 1 day)`).
  - Operating cash flow: purchase / sale / expense collections & payments (`PURCHASE_PAYMENT`, `SALE_COLLECTION`, `EXPENSE_PAYMENT`).
  - Financing cash flow: injections, withdrawals, project funding/refund, loans, worker advances, internal transfers (`CASH_INJECTION_PAYMENT`, `CAPITAL_WITHDRAWAL_PAYMENT`, `PROJECT_FUNDING_PAYMENT`, `PROJECT_REFUND_PAYMENT`, `LOAN_PAYMENT`, `LOAN_REPAYMENT`, `WORKER_ADVANCE_PAYMENT`, `WORKER_ADVANCE_REPAYMENT`, `INTERNAL_TRANSFER_PAYMENT`, correction payments).
  - Investing cash flow: none today (Birth/Death/Capital Gain/Capital Loss are non-cash; value flows via inventory).
  - Closing cash = opening + net cash flow = `balance` (open) / `end_balance` (closed).
- **Current implementation:** a **combined** `cash_in` (total incoming payment txs) and `cash_out` (total outgoing payment txs), plus `previous_balance`/`end_balance`. The operating/investing/financing split is a **future refinement** (Epic 7).
- **Status:** partial — `FinancialPeriod.cash_in` / `cash_out` / `previous_balance` / `end_balance` implemented and shown in the period detail "Cash & Balance" card.

### 3.6 R8 — Statement of Changes in Equity (قائمة التغيرات في حقوق الملكية)

- **Purpose:** explain how equity moved across a period: opening equity → capital contributed → net profit/loss → withdrawals/distributions → closing equity.
- **Scope:** person + project (different drivers, §4).
- **Intended formula:**
  - **Person:** equity = fund balance. Opening equity = `previous_balance`; contributions = `CASH_INJECTION_PAYMENT` + `PROJECT_FUNDING_PAYMENT`; withdrawals = `CAPITAL_WITHDRAWAL_PAYMENT` + `PROJECT_REFUND_PAYMENT`; net profit/loss = capital gain/loss payments (for persons); closing equity = `balance` / `end_balance`.
  - **Project:** equity = contributed capital + retained earnings. Contributed = funding + injections − refunds − withdrawals (payment types); retained earnings = cumulative `profit_loss`; distributions via `DistributionPlan` / `ShareholderAllocation` (models not yet present — future).
- **Status:** not implemented as a page. The inputs (balance, cash flows, P&L) all exist; the dedicated statement is a future Epic 7 deliverable.

### 3.7 Operational summary views (R9–R12)

| # | View | العربية | Formula / content | Implementing code |
|---|------|---------|-------------------|-------------------|
| R9 | Payment Transactions | قائمة المعاملات النقدية | all payment-type txs where entity is source/target, annotated `direction` + `running_balance`, totals incoming/outgoing, current balance | `entity_payment_transactions_view` |
| R10 | Payables detail | تفاصيل الذمم الدائنة | the transactions that build `payables_at`, annotated increase/decrease + running balance + totals | `entity_payables_view` |
| R11 | Receivables detail | تفاصيل الذمم المدينة | mirror of R10 for `receivables_at` | `entity_receivables_view` |
| R12 | Stock value | قيمة المخزون | movement-based `inventory_value` (project only) | `stock_detail` + `stock.inventory_value` |

---

## 4. Entity-type applicability — what matters for persons vs projects

| Metric / report | Person (الشخص) | Project (المشروع) |
|-----------------|----------------|-------------------|
| Fund balance (رصيد الصندوق) | ✓ — the person's wallet | ✓ — project cash position |
| Cash in / out (تدفقات نقدية) | ✓ — injections, withdrawals, funding, refunds, repayments | ✓ — full cash-flow statement (R7) |
| Payables (ذمم دائنة) | ✓ — as client / borrower / debtor | ✓ — purchases, expenses, loans received, advances received |
| Receivables (ذمم مدينة) | ✓ — as vendor / lender / worker / shareholder | ✓ — sales, loans given, advances paid |
| Inventory value (قيمة المخزون) | ✗ — persons hold no stock | ✓ — movement-based stock value (R4/R12) |
| Income Statement / P&L (قائمة الدخل) | ✗ — `profit_loss` raises for non-projects | ✓ — R5, the primary project profitability report |
| Balance Sheet (المركز المالي) | reduced — Assets = balance, Liabilities = 0, Equity = balance | ✓ — R6 full sheet (assets / liabilities / equity) |
| Statement of Changes in Equity (تغيرات حقوق الملكية) | equity = balance (injections − withdrawals) | equity = contributed capital + retained earnings (− distributions) |
| Financial periods (فترات مالية) | ✓ — auto-created open period on activation | ✓ — sequential, closeable periods; the backbone of R5–R8 |
| Loans / worker advances | ✓ — tracked via receivables/payables buckets | ✓ — outstanding_loan_* / outstanding_worker_advance_* on periods |

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
- **Guards:** no-overlap validation per entity; end_date immutable once set; closed periods reject new operations/payments/movements dated inside them (reversals exempt).

---

## 6. Reversal & transaction-type handling

| Report | Reversal policy |
|--------|-----------------|
| Fund balance (R1) | count originals + reversals (signed) — cross-period reversals land in the correct period |
| Payables / receivables (R2/R3) | `_tx_sum_excluding_reversed`: exclude reversal (mirror) rows; exclude originals reversed before `as_of`; include those reversed after `as_of` |
| P&L (R5) | `_signed_sum`: include originals + reversals, negating reversal amounts |
| Cash flow (R7) | payment types only; reversal rows count as cash movement with the original's type/amount |
| Balance sheet (R6) | built from the above per-component rules (as-of `end_date`) |
| Inventory (R4/R12) | `active_movements`: exclude reversal lines and reversed originals; capital valuations exclude reversed operations |

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
