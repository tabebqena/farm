# Automated UI Test Suite — Plan

> **Purpose:** a complete, spec-driven **browser-level (UI)** test suite for the Farm
> Django app. It complements the existing model/engine suites (which pin business
> logic through the ORM and the Django test client) by verifying the **user-visible
> contract**: forms, navigation, flash messages, balances, lists, details, and
> actions.
>
> **Core rule:** every test
> 1. opens a real browser against a live Django server,
> 2. performs the **setup** needed to reach the screen,
> 3. executes **exactly one spec clause** (one action),
> 4. asserts the **visible response** the spec promises.
>
> **One clause → one test method → one assertion family.** This makes the suite
> auditable clause-by-clause against [`docs/specs/`](docs/specs/README.md).

---

## 0. Implementation status (2026-09-01)

**Implemented and green (54 UI tests, `python3 manage.py test ui_tests --keepdb`):**

- **Harness** — `ui_tests/base.py` (`UiTestCase(LiveServerTestCase)`):
  Selenium/headless-Chrome, real-login helper, stable form/amount/select helpers
  (handles the `AmountInputFormatter` visible+hidden amount twin), visible-text
  assertions (CSS-transform aware), pay/repay/reverse/create clause helpers,
  screenshot + HTML artifacts on failure in `test_screenshots/`.
  `selenium==4.47.0` added to `requirements.txt`.
- **Registry** — `ui_tests/manifest.py` (`UI_CLAUSE_MANIFEST`) + a drift-guard
  consistency test; new spec clauses without a UI test fail the build.
- **op_1 Cash Injection** — `ui_tests/operations/test_cash_injection.py` (VC1,
  VC7, SC6, VR5, SR8, SR9 + login smoke).
- **One-shot ops** — `ui_tests/operations/test_one_shot_operations.py`
  (op_2 Cash Withdrawal, op_3 Project Funding, op_4 Project Refund,
  op_7 Internal Transfer, op_15 Correction Credit/Debit): SC/VC/VR5/SR clauses.
- **Payable ops** — `ui_tests/operations/test_payable_operations.py`
  (op_8 Loan, op_11 Worker Advance): SC + A6/A7 pay/repay + VR5.
- **Global** — `ui_tests/global/` (auth: wrong password / `next=` redirect;
  cross-cutting: root redirect, custom 404, EN→AR switch; entities: list + detail
  balance).

**Not yet implemented (tracked as gaps; the harness pattern is established):**

- Feature specs: stock, adjustment (UI section is open in the spec), financial
  period.
- Remaining global flows: project setup wizard, stakeholders, profile edit,
  admin load.

**Implemented since the original status (2026-09-01):**

- op_5 / op_6 Capital Gain & Loss — `ui_tests/operations/test_capital_valuation.py`
  (create + reverse happy path; evaluation `date` field now filled).
- op_12 Expense — `ui_tests/operations/test_expense.py` (create → pay → reverse,
  undoing the payment transaction first per the VR3 guard).
- op_13 Purchase — `ui_tests/operations/test_purchase.py` (wizard create →
  receive → pay → reverse, asserting all visible effects).
- op_14 Sale — `ui_tests/operations/test_sale.py` (dependency-aware: active
  project + received purchase stock + active funded client; wizard create →
  dispatch → collect → reverse, undoing the SALE movement first).
- op_17 Birth / op_18 Death / op_19 Consumption —
  `ui_tests/operations/test_birth.py`, `test_death.py`, `test_consumption.py`
  (create + verify stock event / status / movement + reverse).
- Harness additions in `ui_tests/base.py`: `click_wizard_next`, `goto_query`,
  `fill_date`, `reverse_transaction`; `ui_tests/manifest.py` registers the new
  clauses.
- **UI bug fixed:** `app_operation/snippets/create-form/invoice_formset.html`
  renders the select-mode `selected_product` picker for Death/Consumption forms
  (previously those forms could never be completed in the browser).

---

## 1. Guiding principles

- **Specs are the single source of truth** (repo rule: *where code and spec
  disagree, fix the code, not the spec*). Each spec clause becomes a test.
- Each test is named and documented by the clause it pins (e.g.
  `test_vc1_source_is_world`).
- A machine-checkable manifest (`UI_CLAUSE_MANIFEST`) maps every spec clause to a
  test method, mirroring the executable registry already used by
  `apps/app_operation/tests/base.py` (`COVERAGE_MANIFEST`).
- **Reuse existing fixture factories** (`make_officer`, `make_project`,
  `make_client`, `make_vendor`, `inject_person_fund`, `inject_project_fund`, …) so
  the world the browser sees equals the world the model tests assert on.
- Tests are **idempotent and isolated**: every test builds its own data in
  `setUp()`, never depends on seed data, and leaves no state behind.
- Locators are **stable**: prefer `data-testid`, then `name`, then label text —
  never fragile CSS positional selectors.
- Failures produce a screenshot + page source under `test_screenshots/`.

---

## 2. Stack

- **Selenium WebDriver** driving **headless Chromium**. The task explicitly wants
  "open the browser", so this is a real-browser suite, not a test-client suite.
- **Drivers** are provisioned by **Selenium Manager** (bundled with
  `selenium >= 4.6`) — no manual chromedriver install.
- **`LiveServerTestCase`** (or `StaticLiveServerTestCase`, since the app serves
  `STATICFILES_DIRS`) — Django runs a real server on a random port the browser can
  reach, while staying inside the existing `python3 manage.py test` runner used by
  the repo (see `.roo/rules/testinparallel.md`).
- **New dependency** (add to `requirements.txt`): `selenium>=4.6`.

> **Alternative:** Playwright is viable (auto-installs browsers, richer selectors).
> The harness is driver-agnostic — all clause logic lives in helpers, so the
> browser layer can be swapped without rewriting tests.

### Why not the Django test client?

The existing GET suite ([`docs/testing/GET_REQUEST_TEST_SUITE_SUMMARY.md`](docs/testing/GET_REQUEST_TEST_SUITE_SUMMARY.md))
uses `self.client`, which never executes JS, never proves a rendered form's field
names match the view parser, and never exercises real navigation. The UI suite
pins each spec's **§8 View / UI contract** (routes, pickers, amount source, flash
messages, detail aggregates, reversal alert) that the model suites cannot reach.

---

## 3. Harness architecture

### 3.1 New top-level package: `ui_tests/`

```
ui_tests/
  __init__.py
  base.py                  # UiTestCase: browser lifecycle, login, nav + clause helpers
  manifest.py              # UI_CLAUSE_MANIFEST + drift-guard consistency test
  operations/
    __init__.py
    test_cash_injection.py     # op_1_cash_injection.md
    test_cash_withdrawal.py    # op_2_cash_withdrawal.md
    test_project_funding.py    # op_3_project_funding.md
    test_project_refund.py     # op_4_project_refund.md
    test_capital_gain.py       # op_5_capital_gain.md
    test_capital_loss.py       # op_6_capital_loss.md
    test_internal_transfer.py  # op_7_internal_transfer.md
    test_loan.py               # op_8_loan.md
    test_worker_advance.py     # op_11_worker_advance.md
    test_expense.py            # op_12_expense.md
    test_purchase.py           # op_13_purchase.md
    test_sale.py               # op_14_sale.md
    test_correction.py         # op_15_correction.md (credit + debit)
    test_birth.py              # op_17_birth.md
    test_death.py              # op_18_death.md
    test_consumption.py        # op_19_consumption.md
  features/
    __init__.py
    test_stock.py              # features/stock.md
    test_adjustment.py         # features/adjustment.md
    test_financial_period.py   # features/financial_period.md
  global/
    __init__.py
    test_auth.py               # AUTH-* (manual-test-plan)
    test_entities.py           # ENT-* (manual-test-plan)
    test_crosscutting.py       # GEN-* (language, 404, admin, root redirect)
```

### 3.2 `ui_tests/base.py` — `UiTestCase(LiveServerTestCase)`

Responsibilities:

- **Browser lifecycle.** One headless driver per test class (`setUpClass` /
  `tearDownClass`), `--headless=new`, desktop viewport `1366x768`,
  `implicitly_wait=10`. A `FARM_UI_HEADFUL=1` env var toggles a visible window for
  local debugging; `FARM_UI_BROWSER` overrides the driver.
- **Fixture world.** Import and reuse the factories in
  `apps/app_operation/tests/base.py` (they are pure helpers). `setUp()` builds the
  canonical world: `system`, `world`, `officer`, pre-funded `project`, plus
  whatever each clause needs.
- **Login helper** `login_as_officer()`: drives the **real** login form at
  `/login/`, submits, asserts the redirect — this pins the AUTH contract rather
  than shortcutting with a session.
- **Navigation helpers** `goto`, `open_operation_create(entity, op_type)`,
  `open_detail(op)`, `open_reverse(op)`, `open_payment(op)`, `open_stock(entity)`,
  `open_periods(entity)`, `open_adjustments(op)`.
- **Form helpers** `fill(field, value)`, `select(field, value)`,
  `submit(button_label)`, `assert_flash(text, kind)`, `assert_on_route(name)`.
- **Clause assertion helpers** (spec-driven, visible-response proxies):
  - `assert_visible_text` / `assert_absent`
  - `assert_fund_balance(entity, amount)` — the visible fund-balance badge
  - `assert_operation_row(op, label)` — list entry present
  - `assert_reversal_alert(op)` — `reversal_alert` snippet rendered
  - `assert_stock_qty(entity, product, qty)` — stock-detail card quantity
  - `assert_invoice_total(op, total)` — invoice page totals
  - `assert_error_text(message)` — rendered validation error
- **Failure artifacts.** On any assertion error, write
  `test_screenshots/<ClassName>_<method>_<ts>.png` plus the page HTML source.
- **Stable locators.** Helpers resolve fields by `data-testid` → `name` → label
  text.

### 3.3 `ui_tests/manifest.py`

- `UI_CLAUSE_MANIFEST: list[(spec_id, clause_id, test_path, method_name,
  visible_proxy)]` — one row per clause, mirroring the executable-registry pattern
  in `apps/app_operation/tests/base.py`.
- `TestClauseManifestConsistency` — walks the manifest and fails if any
  `(test_path, method)` does not exist or any spec clause family has no UI test.
  This is the **drift guard**: a spec clause added without a UI test fails the
  build.

---

## 4. Spec → test mapping (one clause = one test)

### 4.1 Operation specs (`docs/specs/operations/op_*.md`)

Each spec defines clause families `VC#` (create-validation), `SC#`
(create-effects), `VR#` (reverse-validation), `SR#` (reverse-effects), `BP#`
(pay guards), `IM#` (immutability). Mapping to UI test shapes:

| Spec clause family | UI test shape |
|---|---|
| `VC#` validation | Open create form → fill valid data except the field under test → submit → assert the spec's *Error* string is rendered and no operation was created |
| `SC#` success effects | Open create form → fill valid data → submit → assert success flash + the promised visible effect (balance badge delta, settlement status, invoice/movement status block) |
| `VR#` reverse-validation | From a created op's detail → open reverse → put the record in the invalid state (already reversed / no reason / reversal of a reversal) → assert the error message + no reversal record |
| `SR#` reverse-effects | Reverse a created op → assert redirect, reversal alert, balance restored (visible badge), settlement cleared (visible status) |
| `BP#` pay guards | Open pay/repay form → attempt blocked / partial / over-payment → assert the guard message + balance unchanged |
| `IM#` immutability | Edit view on a saved op → attempt to change source / destination / amount → assert the immutability error and the field reverts |

Worked example — Cash Injection ([`op_1_cash_injection.md`](docs/specs/operations/op_1_cash_injection.md)):

| Clause | Test method | Action in browser | Visible response asserted |
|---|---|---|---|
| VC1 | `test_vc1_source_is_world` | open `/<person_pk>/cash-injection/create`; try non-world source | `"Cash Injection source must be the World entity."`; no op created |
| VC7 | `test_vc7_amount_positive` | submit amount 0 / negative | `"Amount should be positive, got …"` |
| SC6 | `test_sc6_person_balance_increases` | create with amount 500 | success flash; person fund badge ▲ by 500 |
| SR8 | `test_sr8_person_balance_restored` | create then reverse | balance back to baseline; reversal alert visible |
| VR5 | `test_vr5_reason_required` | reverse with empty reason | error flash; no reversal record |

The same pattern repeats for every operation; the clause catalog comes straight
from each spec's **§9 Branch catalog** and **§10 Test coverage matrix**.

### 4.2 Feature specs

- `features/stock.md` — movement create / receive / dispatch / reverse / query
  clauses: open stock detail → assert cards; receive via the purchase movement
  form; quick-consume; reverse a line → assert quantity restored.
- `features/adjustment.md` — the spec's **UI section is currently open**
  (adjustment form / list / effective amount are `[ ]`). The plan pins the
  *intended* UI contract; where the UI does not yet exist, the test is
  `skipUnless`-guarded with a documented gap (same convention as the specs'
  matrix), so the suite stays green while tracking the missing UI.
- `features/financial_period.md` — period list / detail / close / ledger;
  close-period guards surfaced on create, payment, and movement screens.

### 4.3 Global / auth / entities (from `ai-plans/manual-test-plan.md`)

- `AUTH` — real login, wrong-password error, logout, `?next=` redirect, profile
  edit.
- `ENT` — list filters, person/project create, project setup wizard steps,
  detail badges + fund balance, contact info, stakeholders, category bulk-assign.
- `GEN` — root redirect, EN↔AR language switch, 404 page, admin load.

---

## 5. Response-verification contract (spec effect → visible response)

The suite only asserts what is rendered. Where a spec promises a backend effect
with no visible representation, the UI test asserts the **closest visible proxy**
and leaves the exact-value assertion to the existing model suite (already pinned).
This mapping is recorded per row in `manifest.py` as `visible_proxy`. Examples:

| Spec effect | Visible proxy asserted by the UI test |
|---|---|
| SC1 issuance tx created | detail shows the operation total + settlement status |
| SR4/SR5 counter-transactions | reversal alert + restored balance badge (tx internals pinned by model suite) |
| SC6 balance delta | fund-balance badge on detail/list changes by the exact amount |
| SC9 period auto-assigned | detail shows the covering period; period list shows the op |
| Movement effects (stock) | stock-detail quantity/value cards match the movement |

This keeps the UI suite honest without duplicating the engine suite's exact-value
assertions.

---

## 6. Locators & testability additions

Add stable `data-testid` attributes to high-traffic templates with **targeted,
minimal edits**:

- fund-balance badge on entity detail → `data-testid="fund-balance"`
- flash message container → `data-testid="messages"`
- create-form amount field → `data-testid="amount"`
- operation detail reversal alert → `data-testid="reversal-alert"`
- stock detail quantity card → `data-testid="stock-qty"`

Where an element lacks an id/name, the harness falls back to text-based locators,
so the suite can start before the attribute pass completes.

---

## 7. Execution & reporting

- **Run the UI suite:** `python3 manage.py test ui_tests --keepdb` — serial only
  (`LiveServerTestCase` does not support `--parallel`; the suite is small by
  design).
- **Smoke first:** `python3 manage.py test ui_tests.operations.test_cash_injection --keepdb`.
- **Result capture** (per `.roo/rules/testinparallel.md`): write the full output
  to `tmp/ui-tests-result.txt`, review errors, then **delete the temp file**.
- **Artifacts:** failures write screenshots + HTML source to `test_screenshots/`;
  an optional HTML index groups pass/fail by clause.
- **Visibility:** `FARM_UI_HEADFUL=1` for a visible browser during local runs;
  headless by default.

---

## 8. Maintenance (kept in sync with the specs)

- Any spec edit that adds or changes a clause → the drift-guard test in
  `manifest.py` fails until a UI test + manifest row is added (mirrors the repo's
  executable-manifest convention in `apps/app_operation/tests/base.py`).
- UI-string changes → update only the assertion text. Route changes → update the
  nav helper once.
- After template / locator edits: run `python3 manage.py check` plus the touched
  UI test files.
- Before merge: full engine suite (parallel) **and** the UI suite (serial).

---

## 9. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Flaky timing | Explicit `WebDriverWait` on key elements; no bare `sleep`; stable selectors; generous implicit wait |
| `LiveServerTestCase` incompatible with `--parallel` | Run the UI suite serially, separate from the parallel engine run; document in `docs/testing/README.md` |
| Localization (EN / AR) | Locate by `data-testid` / id (language-neutral); text assertions run under `en`; one cross-cutting test drives the AR switch |
| Missing UI for spec'd features (adjustment UI open items) | `skipUnless`-guarded tests with a documented gap; the manifest keeps them visible |
| Driver / browser availability in CI | Selenium Manager auto-provisions; `FARM_UI_BROWSER` override; document prerequisites |
| Slow full run | One driver per test class; one clause per test keeps each short; smoke subset for quick CI |
| Parallel DB issues with `LiveServerTestCase` | Serial execution + `--keepdb`; no shared mutable state across tests |

---

## 10. Verification & rollout (phased)

1. **Phase 0 — harness proof.** Add `selenium` dep; create `ui_tests/base.py`,
   `ui_tests/manifest.py`, and one smoke test (login + cash-injection create).
   Prove the browser stack runs green.
2. **Phase 1 — one-shot operations.** `op_1`–`op_7`, `op_15`: full
   VC/SC/VR/SR coverage.
3. **Phase 2 — payable / repayable + inventory ops.** `op_8`, `op_11`–`op_14`,
   `op_17`–`op_19`: create, pay/repay, move items, adjust, reverse.
4. **Phase 3 — feature + global.** Stock, adjustment, financial period, auth,
   entities, cross-cutting.
5. **Phase 4 — hardening.** `data-testid` pass, CI wiring, `docs/testing/README.md`
   update.

Each phase ends with: targeted run green → manifest-consistency test green →
full UI suite run → results captured to `tmp/` → temp file deleted.

---

## 11. Open decisions

- **Browser/driver**: Chromium (default) vs Firefox. Chromium chosen for headless
  stability; `FARM_UI_BROWSER` allows Firefox later.
- **Suite location**: top-level `ui_tests/` package (app-agnostic) vs per-app
  `tests/test_ui_*.py`. Top-level package chosen so one clause-domain owns the
  browser harness and the manifest stays in one place.
- **HTML reporting**: optional phase-4 nicety; pytest-html or a minimal custom
  index over `test_screenshots/`.
