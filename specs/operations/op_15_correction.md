# Correction (Credit & Debit)
**Epic:** 10.x — Miscellaneous One-Shot Operations
**Type:** One-shot (`_is_one_shot_operation=True`, `can_pay=False`)

**Concept:** Administrative corrections to a project fund. A Correction Credit adds value to a project fund (system → project), while a Correction Debit removes value from a project fund (project → system). Neither has a category, and both are settled immediately on save.

---

## Correction Credit

**Transaction flow:**
- Issuance: `system.fund → project.fund` — type: `CORRECTION_CREDIT_ISSUANCE` (non-cash)
- Payment: `system.fund → project.fund` — type: `CORRECTION_CREDIT_PAYMENT` (cash, applied on save)

**Entities:**
- Source: the System entity (`source.is_system=True`)
- Destination: a Project entity (`destination.project` must be set)

**Validation:**
- Source must be the System entity (`is_system=True`)
- Destination must be a Project entity
- Both entities must be `active=True`
- Source entity's fund must be `active=True`
- No category (`has_category=False`, `category_required=False`)
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

**Settlement:** Fully settled immediately — `is_fully_settled=True`, `amount_settled == amount`, `amount_remaining_to_settle == 0`

Tasks:
- [x] Verify both `CORRECTION_CREDIT_ISSUANCE` and `CORRECTION_CREDIT_PAYMENT` transactions are created on save
- [x] Verify transaction fund direction: `system.fund → project.fund` for both
- [x] Verify operation is fully settled immediately after creation
- [x] Verify project fund increases by the correction amount
- [x] Verify source must be the System entity (`is_system=True`) — non-system source raises ValidationError
- [x] Verify destination must be a Project entity — non-project destination raises ValidationError
- [x] Verify both entities must be `active=True`
- [x] Verify source fund must be `active=True`
- [x] Verify amount/officer validations (zero, negative, non-staff, inactive, no-user)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `can_pay=False` — `create_payment_transaction()` is blocked after creation
- [x] Verify `has_category=False` and `category_required=False` class-level config
- [x] Verify reversal creates counter-transactions: `project.fund → system.fund`
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify reversal is marked as `is_reversal=True`
- [x] Verify reversal inherits amount, source, destination from original
- [x] Verify counter-transactions preserve transaction type
- [x] Verify project fund is restored to pre-correction balance after reversal
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [ ] UI: create form — source locked to System entity, destination=Project dropdown
- [ ] UI: operation detail shows both transactions and reversal button

---

## Correction Debit

**Transaction flow:**
- Issuance: `project.fund → system.fund` — type: `CORRECTION_DEBIT_ISSUANCE` (non-cash)
- Payment: `project.fund → system.fund` — type: `CORRECTION_DEBIT_PAYMENT` (cash, applied on save)

**Entities:**
- Source: a Project entity (`source.project` must be set)
- Destination: the System entity (`destination.is_system=True`)

**Validation:**
- Source must be a Project entity
- Destination must be the System entity (`is_system=True`)
- Both entities must be `active=True`
- Source entity's fund must be `active=True`
- Source fund must have sufficient balance (`fund.balance >= amount`)
- No category (`has_category=False`, `category_required=False`)
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

**Settlement:** Fully settled immediately — `is_fully_settled=True`, `amount_settled == amount`, `amount_remaining_to_settle == 0`

Tasks:
- [x] Verify both `CORRECTION_DEBIT_ISSUANCE` and `CORRECTION_DEBIT_PAYMENT` transactions are created on save
- [x] Verify transaction fund direction: `project.fund → system.fund` for both
- [x] Verify operation is fully settled immediately after creation
- [x] Verify project fund decreases by the correction amount
- [x] Verify source must be a Project entity — non-project source raises ValidationError
- [x] Verify destination must be the System entity (`is_system=True`) — non-system destination raises ValidationError
- [x] Verify both entities must be `active=True`
- [x] Verify source fund must be `active=True`
- [x] Verify `check_balance_on_payment=False` — balance is not enforced (corrections are admin-only tools for fixing ledger errors; debit succeeds even with insufficient fund balance)
- [x] Verify amount/officer validations (zero, negative, non-staff, inactive, no-user)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `can_pay=False` — `create_payment_transaction()` is blocked after creation
- [x] Verify `has_category=False` and `category_required=False` class-level config
- [x] Verify reversal creates counter-transactions: `system.fund → project.fund`
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify reversal is marked as `is_reversal=True`
- [x] Verify reversal inherits amount, source, destination from original
- [x] Verify counter-transactions preserve transaction type
- [x] Verify project fund is restored to pre-correction balance after reversal
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [ ] UI: create form — source=Project dropdown, destination locked to System entity
- [ ] UI: operation detail shows both transactions and reversal button
