# Changelog

All notable changes to the **farm** project are documented in this file.

The project is a Django-based financial management platform for a livestock farm
business. It tracks money flowing between **Entities** (people, projects, vendors,
clients) through **Operations** (business events) that generate **Transactions**
(ledger entries) against **Funds** (each entity's wallet), with supporting models for
invoices, adjustments, inventory, and evaluations.

Dates follow the commit history (`git log`). The format is loosely based on
[Keep a Changelog](https://keepachangelog.com/en/1.0.0/). The current release version
is tracked in the [`VERSION`](VERSION) file (semantic versioning).

---

## Unreleased / In progress

- No pending changes staged beyond the current `HEAD` (`464f0f4`).

---

## 2026-09-01 — Code quality & refactoring sweep (Phase 2)

A large, mostly behavior-preserving refactoring pass across views, models, and shared
helpers. See [`ai-plans/IMPLEMENTED_PLANS_SUMMARY.md`](ai-plans/IMPLEMENTED_PLANS_SUMMARY.md)
for the consolidated plan record and [`ai-plans/long-function-refactor-phase-2-plan.md`](ai-plans/long-function-refactor-phase-2-plan.md).

### Refactor
- Split long functions/methods project-wide per the phase-2 plan (phases 2–10),
  including the earlier Phase 3 pass.
- Converted function-based views to **class-based views** ([`877c536`]).
- Split [`AddStakeholderView`] into focused methods and added tests ([`0db29c4`]).
- Extracted shared helpers across apps and split long functions ([`6b0e99b`]).
- Moved POST/business logic into models, forms, and shared helpers
  ([`01ad71c`]); decoupled `EvaluationCreateView` from `OperationCreateView`
  ([`8c8baa0`]).
- Consolidated the stock-detail direction queryset into
  `stock.portfolio_direction_q` ([`de14d77`]).
- Removed `Entity.fund` property and its `hasattr` sentinel ([`9d508ef`]).
- Replaced the custom debug/audit machinery with **standard Python logging**
  ([`bc0399e`]).
- Dead-code removal: Phase 0 cleanup ([`7f81264`]), a second cleanup sweep
  ([`c031b11`]), and removal of the dead `initial_period` signal ([`b166923`]).

### Fixed
- Implemented the **VA3 guard**: an item's quantity can no longer shrink below the
  quantity already moved ([`a02eee3`]).

### Docs
- Consolidated implemented `ai-plans/*.md` into
  [`ai-plans/IMPLEMENTED_PLANS_SUMMARY.md`](ai-plans/IMPLEMENTED_PLANS_SUMMARY.md)
  and removed the per-plan files that were fully implemented.
- Fixed broken markdown links across the `docs/` tree ([`921dd01`]).
- Merged the Capital Gain & Capital Loss specs into a single
  `capital_valuation_operation.md` ([`733ba9f`]).
- Added this `CHANGES.md`.

### Other
- Added a [`VERSION`](VERSION) file at the repo root, establishing a semantic
  versioning baseline (`1.0.0`) for the project.

---
 
 ## 2026-08-15 — Reports, operation mixins, proxy merges, UI test suite

### Added
- **Financial statements UI** in a new `apps/app_report` app: hub + Income Statement,
  Balance Sheet, Cash Flow, and Statement of Changes in Equity, period-scoped with
  drill-down links and print-friendly layouts ([`60a1326`]).
- Selenium UI test suite phases: Phase 0 harness + op_1 clauses ([`8fc54c5`]),
  Phase 1 one-shot operations op_2–op_7 / op_15 ([`ad6544a`]), and payable-op /
  global clause tests (loan, worker advance, auth, entities, crosscutting)
  ([`64bf66e`]).

### Refactor
- Extracted inventory behavior from `Operation` into mixins
  (`InventoryOperationMixin`, `StockEventMixin`) ([`ba9c565`]).
- Abstracted one-shot operation config via `OneShotTransactionMixin` ([`0b01b9e`]).
- Merged `CapitalGainOperation` + `CapitalLossOperation` into a single
  `CapitalValuationOperation` proxy ([`982f289`]).
- Merged `CorrectionCreditOperation` + `CorrectionDebitOperation` into a single
  `CorrectionOperation` proxy ([`6fcf4d7`]).

### Other
- "Fast testing" settings optimization for `manage.py test` ([`5173aee`]).

---

## 2026-08-14 — Spec test-pinning & stock-event cleanup

### Fixed
- Strip accounting/transaction mixins from the 5 stock-event operations (Birth, Death,
  Consumption, Capital Gain, Capital Loss) so they no longer create `Transaction`
  rows ([`1d7ff7e`]).
- Replaced the `InvoiceItem` M2M value link for Capital Gain/Loss with a dedicated
  `ProductCapitalValuation` table ([`1bfc930`]).

### Tests
- Closed `op_19` consumption spec coverage gaps ([`2e0ecb5`]).
- Added comprehensive Death (`op_18`) coverage ([`7dc3ba3`]).
- Closed Birth (`op_17`) spec coverage gaps ([`df00a23`]).
- Closed operations spec test-coverage gaps (VR4 guard, SR9/SR10) ([`91f55d6`]).

### Docs
- Pinned every operation contract branch to its test ([`887991a`]).
- Fully rewrote the 5 stock-event operation specs to remove stale transaction/COGS
  references ([`b04d93d`]); synced `stock.md` with the stock-event specs ([`de28a65`]).
- Added the financial reports feature spec ([`514f185`]) and stripped Arabic from it,
  adding model-level calculation recipes ([`34c71c7`]).

---

## 2026-08-13 — Movement-based inventory, sale rework, spec V2 contracts

### Added / Changed
- **Dropped `ProductLedgerEntry`**; stock is now computed from movement lines via
  [`apps/app_inventory/stock.py`](apps/app_inventory/stock.py) ([`10598ac`]).
- **Sale from existing stock**: the sale wizard is now the only sale path, selecting
  the seller's existing products (`f778a77`).
- Moved `MedicalRecord` into a new `apps/app_animal` app ([`f0ad0cf`]).
- Birth double-count fix: made virtual value ops (Birth/Death/Capital Gain/Loss)
  **non-cash** and switched `FinancialPeriod.end_assets` to movement-based inventory
  value ([`c40fc05`]).
- Removed **Profit Distribution & Loss Coverage** operations ([`53901b4`]).
- Allowed purchase operation reversal once payments and movements are reversed
  ([`194ea5b`]).
- External and virtual funds may now pay without balance checks ([`13c5c0e`]).
- Restricted the Birth mother picker to ACTIVE female/mixed animals (VC17)
  ([`9f8e2f2`]).
- Added a red-outlined **Reverse** link beside Print on the operation detail page
  ([`2f72bc0`]).
- Removed dead code ([`a311d83`]).
- Widened nearly every operation spec to the **v2 contract format** (cash injection
  [`5bc51fc`], withdrawal [`2963b36`], funding/refund [`e94e05f`], transfer [`5af8fc1`],
  loan [`055e9cd`], expense [`8787ac6`], purchase [`5fa98ed`], sale [`eef9ec8`],
  correction [`3b6740c`], birth/death [`58362a1`], consumption [`88f1acf`],
  capital gain/loss [`0fbf349`]).

### Tests
- Added focused Internal Transfer tests for SC3, SR9, SR10 ([`3fe2951`]).
- Pinned reversal-op-owns-no-txs (CC35/CD35) for correction ([`9dc53d2`]).
- Closed stock spec coverage gaps in `app_inventory` ([`4c793e0`]).

---

## 2026-08-12 — UI rework, loan fixes, test overhaul

### Added / Changed
- Reworked **stock detail** with per-product physically-present cards, and added a new
  **stock history** page ([`ea403fb`]).
- Marked reversed-born products as removed and enforced product ownership
  ([`09f49eb`]).
- Blocked loan repayment without disbursement and capped repayments by the paid sum
  ([`0fd6150`]).
- Excluded reversal mirrors from payables and receivables ([`d710c41`]).
- Showed source-fund balance on operation and transaction create pages ([`3bbd37d`]).
- Showed payables, receivables, and stock value on the entity detail page ([`c7f587a`]).
- Reworked the operations list with a balance card, statuses, and progress bars
  ([`3498e2f`]).
- Improved operation-detail navigation and settlement actions ([`a334b59`]).
- Restored the repaid state after a repayment transaction is reversed ([`fdb8cfb`]).
- Added an entity transactions list view for balance tracking ([`a3d841a`]).

### Tests
- Overhauled the operation test suite with granular one-side-effect-per-test coverage
  ([`a628b08`]).
- Added the internal entity stock-transfer plan and updated the TODO tracker
  ([`a3b799b`]).

---

## 2026-08-10/08-11 — Animal tracking, seeding, integrity

### Added
- Animal tracking fields on `ProductTemplate` / `Product` and a new `MedicalRecord`
  model ([`e0c4605`], [`519f100`], [`eb7df55`]).
- Captured newborn gender, birth date, and mother in birth operations ([`48a2aa9`]).
- Seeded animal templates by **species × stage × gender** ([`869790b`]).
- Individual-animal tracking, closed-period guards, and inventory-integrity fixes
  ([`4b74127`]).
- Improved login redirect behavior ([`f67c10f`]).

---

## 2026-05 — Financial periods, logging, UI test expansion

### Added / Changed
- Added financial-period views and balance-calculation methods ([`666df06`]).
- Refactored `FinancialPeriod` lifecycle to automatic reconciliation ([`f3bd8db`]) and
  converted `FinancialPeriod.amount` from a stored field to a calculated property
  ([`b2cf717`]).
- Blocked manual period creation for active entities with existing periods
  ([`65b36df`]) and switched the period-creation guard to a redirect-with-messages
  ([`024aed6`]).
- Added a comprehensive navigation row across all views ([`035044d`]).
- Applied comprehensive logging across the entire project ([`77199e1`], [`8aef009`]),
  with test-mode guards on `DebugContext` ([`2494a4a`]).
- `InvoiceItem` now respects adjustments ([`3b44432`]); flattened products on deferred
  movement ([`ccf53cb`]).
- Added paid/remaining amount columns to the operation list ([`39afd97`]).

### Tests
- Expanded the UI test suite to cover 10 key views across all modules ([`80ebec0`]) and
  fixed viewport/authentication handling ([`66efaf5`]).
- Split test files into one file per test class (29 → 135 files) ([`e7a71b6`]).

---

## 2026-04 — Core implementation & early tests

### Added
- Project setup and the personal-operation model ([`3bdb63e`]).
- Expense & financial categories ([`dde5cd8`]).
- Adjustments implementation ([`df0d558`]).
- Fixed the post-save task dispatch key matching in `BaseModel` / `Operation`
  ([`70fce21`]) and the purchase wizard ([`fabedda`]).

### Tests
- Cash-injection test ([`0652051`]), AI tests ([`c79548d`]), test suites for
  Capital Loss / Internal Transfer / Loan and spec-file renames ([`3545b93`]),
  financial-period tests ([`76c7e57`]), and distribution-plan tests ([`39277a9`]).

---

## 2026-03 — Project inception

- Initial Entity model & views (person, project, category, fund) ([`c23fd37`]).
- Moved "get related entities" logic to the operation proxy ([`bc7631f`]).
- Fixes to adjustments ([`07b132e`]).
- Expense & categories groundwork ([`dde5cd8`]).



## How this file is maintained

- Grouped by date (most recent first), then by type (Added / Changed / Fixed / Tests /
  Docs / Refactor / Other).
- References the relevant git commit(s) and related planning documents in
  [`ai-plans/`](ai-plans/).
- For feature-level behavior, see the specs in [`docs/specs/`](docs/specs/) and the
  consolidated [`ai-plans/IMPLEMENTED_PLANS_SUMMARY.md`](ai-plans/IMPLEMENTED_PLANS_SUMMARY.md).
