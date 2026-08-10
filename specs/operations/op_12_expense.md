# Expense
**Epic:** 11.3 — Payable Operations
**Type:** Payable (`can_pay=True`, `is_partially_payable=True`, category required)

**Concept:** Records an obligation to pay for a service or product purchased from an unregistered (world) vendor.

**Transaction flow:**
- Issuance: records expense obligation — type: `EXPENSE_ISSUANCE` (non-cash, does NOT affect fund balances)
- Payment: `project.fund → world.fund` — type: `EXPENSE_PAYMENT` (cash movement, deducts from project fund)
- Payments can be made in multiple partial installments up to the total amount

**Entities:**
- Source: a Project entity (`source.project` must be set)
- Destination: the World entity (`destination.is_world=True`)

**Actions:** create, pay, adjust, reverse.

## create
**Validation:**
- Source must be a Project entity
- Destination must be the World entity (`is_world=True`)
- Both entities must be `active=True`
- Source entity's fund must be `active=True`
- Category is required (`has_category=True`, `category_required=True`); category type must be `EXPENSE`
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`
- Balance @ create: **exempt** (issuance unguarded); not one-shot

**Success effects:**
- `EXPENSE_ISSUANCE` created on save (non-cash obligation)
- No payment on save — payments happen later via **pay**
- No product ledger entries / no movement lines

## pay
**Validation:**
- Balance enforced per payment (`check_balance_on_payment=True`)
- Amount > 0 and ≤ remaining
- Partial allowed — multiple payments
- Over-payment guard

**Success effects:**
- `EXPENSE_PAYMENT` (`project.fund → world.fund`)
- ▼ project → ▲ world; `amount_settled` ↑

## adjust
**Validation:**
- `can_adjust=True`; not reversed / not a reversal
- Adjustment type allowed for EXPENSE
- Amount > 0; officer staff + active

**Success effects:**
- `EXPENSE_ADJUSTMENT_INCREASE` / `EXPENSE_ADJUSTMENT_DECREASE` (non-cash)
- `effective_amount` delta (no inventory ledger entries)

## reverse
**Validation:**
- Not already reversed / not a reversal / reason required
- Blocked if any payment (`EXPENSE_PAYMENT`) exists
- Blocked if any non-reversed adjustment exists

**Success effects:**
- Reversal record; counter-transaction for issuance only

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

**Category note:** `has_category=True` and `category_required=True` are enforced as class-level config **and** at the model level via the `Operation.category` FK (`Operation.clean()` requires a category and validates `category_type`). A `FinancialCategory` with `category_type="EXPENSE"` must be linked to the project entity.

Tasks:
- [x] Verify save creates only one EXPENSE_ISSUANCE transaction (not payment — not one-shot)
- [x] Verify no EXPENSE_PAYMENT transaction is created on save
- [x] Verify EXPENSE_ISSUANCE direction: source=project.fund, target=world.fund
- [x] Verify EXPENSE_ISSUANCE is non-cash: project fund balance unchanged after save
- [x] Verify amount_remaining_to_settle equals full amount after creation
- [x] Verify is_not_fully_settled after creation
- [x] Verify source must be a Project entity (non-project source raises ValidationError)
- [x] Verify source must be active (inactive source raises ValidationError)
- [x] Verify source fund must be active
- [x] Verify destination must be the World entity (non-world destination raises ValidationError)
- [x] Verify amount/officer validations (zero, negative, non-staff, inactive, no-user)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `has_category=True` and `category_required=True` class-level config
- [x] Verify FinancialCategory with type EXPENSE can be created for the project entity
- [x] Verify payment creates EXPENSE_PAYMENT transaction (direction: project.fund → world.fund)
- [x] Verify payment amount_remaining_to_settle decreases correctly
- [x] Verify multiple partial payments are allowed and accumulate
- [x] Verify full payment marks operation as fully settled
- [x] Verify project fund decreases by payment amount (EXPENSE_PAYMENT is cash)
- [x] Verify payment cannot exceed remaining amount (over-payment raises ValidationError)
- [x] Verify zero/negative payment raises ValidationError
- [x] Reversal: reverses issuance counter-transaction only (payment transactions block reversal)
- [x] Verify reversal creates reversal operation with correct linkage
- [x] Verify reversal marks original as reversed
- [x] Verify reversal is marked as is_reversal
- [x] Verify reversal inherits amount, source, destination from original
- [x] Verify reversal creates exactly 1 counter-transaction (for issuance only)
- [x] Verify reversal counter-transaction flips source/target funds
- [x] Verify project fund unchanged after reversal (issuance is non-cash)
- [x] Verify reversal is blocked when any EXPENSE_PAYMENT transaction exists
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [x] Add FK from Operation to FinancialCategory to enforce category_required at model save level (migration `0008_operation_category`; enforced in `Operation.clean()`; view passes `category_id` into `Operation.create()`)
- [ ] UI: create form — source=Project (url entity), destination=World (auto), category dropdown (required, type=EXPENSE)
- [ ] UI: detail shows category, amount paid, remaining; "Record Payment" button
