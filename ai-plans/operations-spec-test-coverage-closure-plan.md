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
