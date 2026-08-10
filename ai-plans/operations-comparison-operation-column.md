# Plan — Clarify operation codes in operations-comparison.md

**File:** `specs/operations/operations-comparison.md`

## Goal

Several tables and prose sections in the comparison document use only the short
operation codes (CI, CW, PF, PR, CG, CL, IT, LN, PD, LC, WA, EX, PU, SA, CC, CD,
BI, DE, CO) as row labels / inline tokens. Add the full operation name so each
code is self-explanatory.

## Plan

- Add a new **Operation** column (full name) immediately after the `Op` (code)
  column in **all 19 tables** that use short codes as row labels:
  - Action applicability table
  - Matrix 1.1 Groups A, B, C
  - Matrix 1.2–1.7 (validation)
  - Matrix 2.1 Groups A, B, C
  - Matrix 2.2–2.7 (success effects)
- Keep the existing `Op` code column unchanged.
- Full names taken verbatim from the "Operation reference" table
  (CI = Cash Injection, …, CO = Consumption).
- Placeholder rows (`(others)`) in Matrix 1.3 and 2.5 get `—` in the Operation cell.
- Update prose that uses short codes with the full name in parentheses:
  - "Extra create validation not captured by the generic columns" (PR, PD, LC, EX)
  - "Summary highlights (per action)" (all code lists)
- Matrix 3 per-operation reports already spell out full names in headings — no change.

## Implemented

- Added `Operation` column to the Action applicability table (all 19 rows).
- Added `Operation` column to Matrix 1.1 Group A (Entity structure), Group B
  (State & funds), Group C (Business constraints & lifecycle).
- Added `Operation` column to Matrix 1.2 (Reverse validation), 1.3 (Adjust),
  1.4 (Move items), 1.5 (Adjust items), 1.6 (Pay), 1.7 (Repay).
- Added `Operation` column to Matrix 2.1 Group A (Ledger & settlement), Group B
  (Fund balance deltas), Group C (Inventory, plan & lifecycle).
- Added `Operation` column to Matrix 2.2 (Reverse effects), 2.3 (Adjust effects),
  2.4 (Move items effects), 2.5 (Adjust items effects), 2.6 (Pay effects),
  2.7 (Repay effects).
- `(others)` placeholder rows in Matrix 1.3 and 2.5 now show `—` in the Operation cell.
- Prose: "Extra create validation" bullets now read e.g. `**PR** (Project Refund) — …`.
- Prose: "Summary highlights" code lists now include full names, e.g.
  `CI (Cash Injection), CG (Capital Gain), …`.
- Verified all 19 tables have balanced markdown column counts after the edit.
