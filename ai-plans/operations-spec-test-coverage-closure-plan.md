# Operations Spec — Test-Coverage Closure Plan

## Goal

Walk through the operation contracts in `docs/specs/operations/` and close every
remaining clause that had **no dedicated pinning test**, so each contract clause
has its own test.

## Scope

All 19 operation specs (`op_1` … `op_19` + `operations-comparison.md`) were
reviewed against the existing suite under `apps/app_operation/tests/` plus the
shared engine, inventory, adjustment, and transaction suites.

## Pre-existing state

- The suite was already comprehensive (baseline: 1339 tests, all passing).
- Most validation/effect clauses were already pinned by per-operation create /
  reverse / pay / repay tests and the executable `COVERAGE_MANIFEST` in
  `apps/app_operation/tests/base.py`.

## Gaps identified and closed

1. **Reversal dependency guard (VR4)** — `Operation.reverse()` raises
   `"Cannot reverse this operation: its products were moved again in a later
   operation."` when a DEATH/CONSUMPTION/SALE product was moved again in a later
   outbound operation. No test pinned it.
   - Added `ConsumptionReversalTest.test_reversal_blocked_when_product_moved_again_in_later_consumption`
     (partial consumption then full write-off — the realistic scenario, since
     **consumption is partially-consumable**).
   - Added `SaleCreateFromSessionStockTest.test_reversal_blocked_when_product_moved_again_in_later_sale`
     (partial sale then full disposal).
   - **Death (op_18 VR4)** — there is **no partial death** (a death always writes
     off the full INDIVIDUAL animal, which then becomes terminal DEAD and is
     blocked from later moves by `Product.validate_active()`). The branch is a
     **defensive guard, unreachable via normal flows**; the shared code path is
     pinned by the SALE and CONSUMPTION tests. Spec updated to say so (removed
     the stale `TODO(test)`).

2. **SR9 "settlement state cleared" + SR10 "reason flows to reversal"** — flagged
   as "no dedicated focused test yet" in `op_2`, `op_3`, `op_4`, `op_15`.
   - Added `test_reversal_clears_settlement_state` and
     `test_reason_flows_to_reversal_description` to the reversal suites of:
     Cash Withdrawal, Project Funding, Project Refund, Correction Credit,
     Correction Debit.

3. **Specs are link-free** — per repo convention, specs reference code/tests by
   **plain name only** (no markdown `[symbol](path)` links, no `file.py:NN`), so
   renames never break a spec. Added/updated pinning references as plain names.

## Manifest

Registered every new test in `COVERAGE_MANIFEST` (base.py) so the executable
branch registry cannot drift:
- `(CONSUMPTION, reverse, VR4)`
- `(SALE, reverse, VR4b)`
- `(CASH_WITHDRAWAL | PROJECT_FUNDING | PROJECT_REFUND | CORRECTION_CREDIT |
  CORRECTION_DEBIT, reverse, SR9/SR10)`

## Verification

- Targeted runs of every touched test file: OK.
- Full suite: `python3 manage.py test --parallel=10 --keepdb` →
  **1373 tests, OK** (was 1339).

---

## Coverage-documentation completion pass (docs only — 2026-08-14)

Follow-up pass to make the **documented** coverage of `docs/specs/operations/`
complete and verifiable, so the spec's §10 "Test coverage matrix" and the
"Pinned by test" / "Verified by" columns are fully populated with **real** test
method names (plain names, `ClassName.method` — no markdown links).

### What was done

- Filled every previously-empty **"Pinned by test"** / **"Verified by"** cell in the
  validation/effect tables **and** every empty **§10 "Test method"** cell for:
  `op_1` (Cash Injection), `op_2` (Cash Withdrawal), `op_3` (Project Funding),
  `op_4` (Project Refund), `op_5` (Capital Gain), `op_6` (Capital Loss),
  `op_8` (Loan), `op_11` (Worker Advance), `op_12` (Expense),
  `op_13` (Purchase), `op_14` (Sale), `op_15` (Correction Credit/Debit),
  `op_19` (Consumption).
- Completed `op_7` (Internal Transfer) — its §10 matrix was already complete;
  the per-branch validation/effect pins were added for consistency.
- `op_17` (Birth) and `op_18` (Death) were already fully pinned — untouched.
- Shared branches (period contract, tx engine, adjustment engine, inventory
  guards) now cite the shared suites explicitly
  (`OperationPeriodAssignmentTest`, `DownstreamClosedPeriodGuardTest`,
  `AdjustmentValidationTest`/`AdjustmentReversalTest`/`AdjustmentEffectiveAmountTest`,
  `InventoryMovementCreationTest`, `ProductCapitalValuationModelTest`, …).
- No **new** tests were required: the existing suite already covered every
  branch; the gap was in the **documentation** of that coverage, not in code.
- Fixed two stale class-name references to the real classes
  (`ValidationTest` for invoice-item adjustment validation; the commodity
  single-line movement test lives on `InventoryMovementModelContractTest`).

### Verification

- Automated checker (`/tmp/verify_spec_refs.py`) parsed **every**
  `ClassName.test_method` reference in `docs/specs/operations/` and confirmed
  all **699** resolve to a real test class + method in the suite; all bare
  `test_…` references resolve to real test methods (remaining bare tokens are
  test **file** names, allowed by the plain-name convention).
- `python3 manage.py check` → no issues.
- Full suite: `python3 manage.py test --parallel=10 --keepdb` →
  **1432 tests run**; the only failures are pre-existing Selenium **UI**
  `ui_tests.operations.test_cash_injection` LiveServer login-timeout cases
  (headless-browser environment), unrelated to this docs-only pass. All
  operation model/view suites and `CoverageManifestTest` pass.
- Temporary test-output files under `tmp/` were removed after review.
