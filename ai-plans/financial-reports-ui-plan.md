# Plan: Expose Financial Reports in the UI

## Goal
Add the **four accounting statements** (Income Statement, Balance Sheet, Cash Flow, Statement of
Changes in Equity) to the UI, scoped per entity and per financial period, reusing the existing
model properties and the formulas already contracted in
[`docs/specs/features/financial_reports.md`](../docs/specs/features/financial_reports.md)
(reports **R5–R8**, §3.3–§3.6, §7 "Future (Epic 7)").

This plan implements the spec's future items:
- dedicated Income Statement / Cash Flow / Equity pages (Balance Sheet is partially shown in the
  period detail "Period Summary"),
- the operating / investing / financing split of the cash flow,
- the full balance-sheet reconciliation (fold `payables_at` / `receivables_at` into assets/liabilities).

Reports **R1–R4** and **R9–R12** (balance, payables, receivables, inventory value, payment
transactions, stock) are already in the UI and are only linked from the new report hub — no rework.

## Decisions
- **New Django app `apps/app_report`** (registered as `"apps.app_report"` in `INSTALLED_APPS`,
  included in `farm/urls.py` under `reports/`) to isolate the read-only reporting surface and its
  tests — matches the repo's one-app-per-domain convention (`app_operation`, `app_transaction`,
  `app_inventory`, …).
- **No schema changes / no migrations.** All figures derive from existing models
  (`Entity`, `Transaction`, `TransactionType`, `FinancialPeriod`, `InventoryMovementLine`,
  `Product`, `ProductCapitalValuation`) via existing properties plus thin **computation helpers**
  in `apps/app_report/reporting.py`. The models stay the source of truth; the helpers only
  *compose* them (line-item breakdowns, cash-flow categories, equity components) — those helpers
  are new implementing code for the spec's formulas and must be test-pinned.
- **Period-scoped.** Each statement is shown for a selected `FinancialPeriod` (default: the open
  period; fallback: latest). Selector is a GET dropdown `?period=<pk>` validated to belong to the
  entity.
- **Entity-type gating** follows the spec §4: project ⇒ all four statements; person ⇒ Cash Flow
  and Equity only (Income Statement / Balance Sheet are project-only by contract).
- **Accounting-style presentation + drill-downs.** Each statement renders in the standard
  accounting layout (statement title, "For the period ended …" / "As of …" header, section
  subtotals, grand totals, currency, double-rule totals) and every significant line item links to
  the page that proves it (payables, receivables, payment transactions, stock, operation list,
  period ledger). This makes the statements both formal and auditable.
- **Print-friendly.** Report pages hide chrome under `@media print` so they can be printed/shared.

## Files

### New
| File | Purpose |
|------|---------|
| `apps/app_report/__init__.py` | package marker |
| `apps/app_report/apps.py` | `AppReportConfig(name="apps.app_report")` |
| `apps/app_report/views.py` | `reports_hub_view`, `income_statement_view`, `balance_sheet_view`, `cash_flow_view`, `equity_statement_view` |
| `apps/app_report/reporting.py` | computation helpers (see below) |
| `apps/app_report/urls.py` | report routes |
| `apps/app_report/tests.py` | view + helper tests |
| `apps/app_report/templates/app_report/report_hub.html` | report hub |
| `apps/app_report/templates/app_report/income_statement.html` | income statement |
| `apps/app_report/templates/app_report/balance_sheet.html` | balance sheet |
| `apps/app_report/templates/app_report/cash_flow.html` | cash flow statement |
| `apps/app_report/templates/app_report/equity_statement.html` | equity statement |
| `apps/app_report/templates/app_report/_report_header.html` | shared header (entity, period range, currency, print button, back-to-hub) |

### Changed
| File | Change |
|------|--------|
| `farm/settings.py` | add `"apps.app_report"` to `INSTALLED_APPS` |
| `farm/urls.py` | `path("reports/", include("apps.app_report.urls"))` (inside `i18n_patterns`) |
| `apps/app_base/navigation.py` | NAVIGATION_MAP entries for the 5 report views + related links |
| `apps/app_entity/templates/app_entity/entity_detail.html` | add a "Financial Reports" button next to "Payment Transactions" / "Stock" (project + person) |
| `apps/app_operation/templates/app_operation/period_detail.html` | add links to Income Statement / Balance Sheet / Cash Flow for the current period |
| `apps/app_transaction/views.py` | `entity_payment_transactions_view` gains an optional `?type=<TransactionType>` filter so report line items can deep-link to a specific transaction type |
| `docs/specs/features/financial_reports.md` | (after implementation) move R5–R8 status from "future" to "implemented", register the new views/templates in §2.4 and §7 |

## Routes (`apps/app_report/urls.py`)

| URL | View | Name |
|-----|------|------|
| `reports/<int:entity_pk>/` | `reports_hub_view` | `report_hub` |
| `reports/<int:entity_pk>/income-statement/` | `income_statement_view` | `income_statement` |
| `reports/<int:entity_pk>/balance-sheet/` | `balance_sheet_view` | `balance_sheet` |
| `reports/<int:entity_pk>/cash-flow/` | `cash_flow_view` | `cash_flow` |
| `reports/<int:entity_pk>/equity/` | `equity_statement_view` | `equity_statement` |

All views are function-based, decorated `@login_required` + `@debug_view`, load the entity with
`get_object_or_404(Entity, pk=entity_pk, error_message="Entity not found or has been deleted.")`,
resolve the selected period from `request.GET.get("period")` (404 if it does not belong to the
entity), set `request.navigation_overrides` (entity display name, like `period_list_view`), and
`render(request, "app_report/<report>.html", context)`. Project-only views return a 403
(`PermissionDenied`) for non-project entities instead of rendering.

## Computation helpers (`apps/app_report/reporting.py`)

Each helper takes the resolved `period` (or `entity` + `as_of`) and returns a dict of line items.
They reuse the spec's buckets verbatim (reverse-aware signed sums; `TransactionType` sets).

- `income_statement(period)` → `{income: {type: amount, ...}, income_total, costs: {...},
  costs_total, net}` — same type buckets as `Entity.profit_loss` (§3.3), with `signed(amount)`
  negating reversal rows and `date ∈ [start, end)`.
- `balance_sheet(period)` → `{cash, inventory, receivables, assets, payables, liabilities,
  equity}` — the **intended** full sheet (§3.4): `assets = cash + receivables + inventory`,
  `liabilities = payables`, `equity = assets − liabilities`. Uses `balance_at`, `receivables_at`,
  `payables_at` (as-of `period.as_of`) and `stock.inventory_value`. Loans/advances are **not**
  added separately (already inside receivables/payables — no double count). For an open period,
  the current subset `end_assets`/`end_liabilities` stays available on the period detail page.
- `cash_flow(period)` → `{opening, operating: {in, out}, financing: {in, out}, investing:
  {in, out}, net, closing}` — payment types grouped by the §3.5 category map (operating =
  purchase/sale/expense payments; financing = injections, withdrawals, funding/refund, loans,
  advances, internal transfer, corrections; investing = none today). `opening = previous_balance`,
  `closing = balance`/`end_balance`.
- `equity(period)` → for a **person**: `{opening, contributions, withdrawals, net_change,
  closing}` (contributions = `CASH_INJECTION_PAYMENT` + `PROJECT_FUNDING_PAYMENT` incoming,
  withdrawals = `CAPITAL_WITHDRAWAL_PAYMENT` + `PROJECT_REFUND_PAYMENT` outgoing, §3.6); for a
  **project**: `{contributed_capital, retained_earnings, closing}` (contributed = financing
  payment in − out; retained = cumulative `profit_loss` over closed periods; closing = balance
  sheet equity).

## Templates

- All extend `base.html`, load `i18n`, render amounts as `{{ currency }} {{ value|floatformat:2 }}`
  with `currency = settings.CURRENCY_SYMBOL` (context already carries it on the entity detail view;
  report views add it too).
- `_report_header.html`: statement title, entity name (link to entity detail), a formal date line
  ("For the period ended {end}" when closed / "As of {today}" when open), period range, currency,
  a period **selector** (GET dropdown of `entity.financial_periods.all().order_by("-start_date")`,
  preselecting the current period), a "Back to Reports" link, and a `@media print` rule hiding
  `.no-print` chrome.

### Accounting layouts (per statement)

Each statement uses the standard single-column accounting layout — **label in the left column,
amount in the right column, section headings, subtotals, bold grand totals with a double rule**:

- **Income Statement** (`income_statement.html`)
  - *Revenue*: sale issuance, purchase issuance (project as vendor), correction credit, sale
    adjustment increases, purchase adjustment increases → **Total Revenue**
  - *Costs & Expenses*: purchase issuance, expense issuance, sale issuance (project as client),
    correction debit, adjustments → **Total Costs & Expenses**
  - **Net Profit / (Loss)** = Total Revenue − Total Costs & Expenses (green `+` / red `−`)
- **Balance Sheet** (`balance_sheet.html`) — vertical Assets / Liabilities / Equity:
  - *Assets*: Cash & fund balance, Receivables, Inventory → **Total Assets**
  - *Liabilities*: Payables → **Total Liabilities**
  - *Equity*: contributed capital + retained earnings (= Assets − Liabilities) → **Total Equity**
  - Footer reconciliation: **Total Assets = Total Liabilities + Total Equity**
- **Cash Flow Statement** (`cash_flow.html`)
  - **Beginning cash** (opening balance)
  - *Operating activities*: in / out → net
  - *Financing activities*: in / out → net
  - *Investing activities*: in / out → net (0 today)
  - **Net increase / decrease in cash** → **Ending cash** (= closing balance)
- **Statement of Changes in Equity** (`equity_statement.html`)
  - Person: beginning equity → + contributions → − withdrawals → **ending equity**
  - Project: contributed capital → + retained earnings → **ending equity** (= balance-sheet equity)

### Drill-down links (line item → proving page)

| Line item | Link target |
|-----------|-------------|
| Cash / fund balance | `entity_payment_transactions_list` |
| Receivables | `entity_receivables_list` |
| Payables | `entity_payables_list` |
| Inventory value | `stock_detail` (project) |
| Income / cost lines | `operation_list_view` (scoped to the entity) and, where a single type matters, `entity_payment_transactions_list?type=<TX_TYPE>` (new optional filter) |
| Loans / advances lines | `entity_receivables_list` / `entity_payables_list` |
| Period P&L / end balance | `period_detail_view` / `period_ledger_view` |

- Hub: cards linking to the available reports (project shows all four, person shows Cash Flow +
  Equity) and to the already-existing pages (payment transactions, payables, receivables, stock
  for projects), plus the period selector and a small legend of the as-of date.

## Navigation (`apps/app_base/navigation.py`)

Add NAVIGATION_MAP entries:

| View name | Title | Icon | Parent |
|-----------|-------|------|--------|
| `report_hub` | Financial Reports | `bi-bar-chart-line` | `("Entities", "entity_list")` |
| `income_statement` | Income Statement | `bi-graph-up-arrow` | `("Reports", "report_hub", {"entity_pk": "entity_pk"})` |
| `balance_sheet` | Balance Sheet | `bi-columns-gap` | `("Reports", "report_hub", {"entity_pk": "entity_pk"})` |
| `cash_flow` | Cash Flow | `bi-arrow-left-right` | `("Reports", "report_hub", {"entity_pk": "entity_pk"})` |
| `equity_statement` | Equity Statement | `bi-pie-chart` | `("Reports", "report_hub", {"entity_pk": "entity_pk"})` |

Add `("Reports", "report_hub", {"entity_pk": "entity_pk"})` (or `{"pk": "pk"}` for
`entity_detail`) to the `related` lists of `entity_detail`, `entity_payment_transactions_list`,
`entity_payables_list`, `entity_receivables_list`, `period_list_view`, `period_detail_view`, and
`operation_list_view`.

## Tests (`apps/app_report/tests.py`)

Seed with the repo test helpers (`_make_officer`, `Entity.create`, operation factories from
`apps/app_operation/tests/base.py` and `apps/app_inventory/tests/general.py`).

- **Hub**: auth redirect; 404 for missing entity; project lists 4 statements; person lists 2;
  selector lists periods; default period is the open one.
- **Income statement**: purchase + expense + sale + correction produce correct income/costs/net
  rows; a reversal moves the number to the opposite sign; non-project → 403; `?period=` scoping.
- **Balance sheet**: `assets = cash + inventory + receivables`, `liabilities = payables`,
  `equity = assets − liabilities` (reconciliation invariant); a purchase that is not yet paid
  raises payables (and receivables on the vendor's side); inventory counted; loans/advances not
  double-counted.
- **Cash flow**: opening/closing reconcile with `previous_balance`/`end_balance`; operating vs
  financing split; a cash injection lands in financing; person entity works.
- **Equity**: person contributions/withdrawals; project contributed capital + retained earnings;
  closing equals balance-sheet equity.
- **Entity detail**: "Financial Reports" button present (extend
  `test_views_get_entity_detail_view.py`).
- **Drill-downs**: each statement template renders the expected links — receivables/payables lines
  → `entity_receivables_list` / `entity_payables_list`; balance line → `entity_payment_transactions_list`;
  inventory line → `stock_detail`; income/cost lines → `operation_list_view` (and the typed
  `?type=` transaction filter when used); period figures → `period_detail_view` / `period_ledger_view`.

## Verification

```
python manage.py check
python manage.py test apps.app_report --parallel=10      # first run after adding the app
python manage.py test apps.app_report --parallel=10 --keepdb
python manage.py test apps.app_entity.tests.test_views_get_entity_detail_view apps.app_operation.tests.period
```

Capture output into `tmp/` and delete it after inspecting (per repo testing rules).

## Notes
- Reuse existing `FinancialPeriod` helpers (`as_of`, `previous_balance`, `balance`,
  `end_balance`, `is_closed`) — do not reimplement them.
- Reversal rules come from the spec §6 (balance/P&L count reversals signed; payables/receivables
  exclude them). The helpers must mirror those rules exactly.
- No data migrations; no changes to existing models.

## Implemented (2026-08-15)
- Created `apps/app_report` — `AppReportConfig` registered as `apps.app_report` in
  `INSTALLED_APPS`; `farm/urls.py` includes it under `reports/`.
- `apps/app_report/reporting.py`: `income_statement`, `balance_sheet`, `cash_flow`, `equity`
  helpers using the spec's type buckets and reversal-aware signed sums.
- `apps/app_report/views.py`: `reports_hub_view`, `income_statement_view`,
  `balance_sheet_view`, `cash_flow_view`, `equity_statement_view` (`@login_required` +
  `@debug_view`, `?period=` scope, project-only 403 for Income Statement / Balance Sheet).
- Routes: `reports/<entity_pk>/`, `.../income-statement/`, `.../balance-sheet/`,
  `.../cash-flow/`, `.../equity/`.
- Templates under `apps/app_report/templates/app_report/`: `_report_styles.html`,
  `_report_header.html`, `report_hub.html`, and the four statement pages — accounting-style
  layouts with drill-down links and `@media print`.
- `apps/app_base/navigation.py`: NAVIGATION_MAP entries for the hub + four statements and
  "Reports" related links on entity detail, payment transactions, payables, receivables,
  operations, and periods.
- `entity_detail.html`: "Financial Reports" button. `period_detail.html`: Income Statement /
  Balance Sheet / Cash Flow links for the period.
- `apps/app_transaction/views.py` + `entity_payment_transactions.html`: optional `?type=`
  filter with a banner (drill-downs); fixed the stray `12.` prefix on the template's first line.
- Tests in `apps/app_report/tests.py` (22 tests). Spec updated in
  `docs/specs/features/financial_reports.md` (§1, §2.4, §2.5, §3, §7, §8) marking R5–R8
  implemented.
- Verification: `manage.py check` clean; `apps.app_report` 22/22; affected suites
  (app_transaction, entity-detail view, app_operation.period, app_base) 176/176.
