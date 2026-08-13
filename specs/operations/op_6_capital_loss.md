# Capital Loss
**Epic:** 10.3 — Miscellaneous One-Shot Operations
**Type:** One-shot
**Transaction flow:**
- Issuance: `entity → system.fund` — type: `CAPITAL_LOSS_ISSUANCE`
- Payment: `entity → system.fund` — type: `CAPITAL_LOSS_PAYMENT` — **non-cash bookkeeping** (excluded from `payment_types()`; the payment never affects the entity's fund balance)

**Settlement:** Fully settled immediately — `is_fully_settled=True`, `amount_settled == amount`, `amount_remaining_to_settle == 0`

**Actions:** create, reverse.

## create
**Validation:**
- Destination must be the System entity (`is_system=True`)
- Source entity must be `active=True`
- Source entity's fund must be `active=True`
- **No fund-balance requirement** — a project may record a capital loss even when its balance is zero or insufficient (`check_balance_on_payment=False`). A loss-making project can go further into deficit.
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`
- One-shot auto-settled — payment transaction fires on save (`E@create` pay)

**Success effects:**
- `CAPITAL_LOSS_ISSUANCE` + `CAPITAL_LOSS_PAYMENT` created on save
- Immediately settled (`is_fully_settled=True`)
- Fund deltas: **no cash flow** — ▼ entity (inventory value only) → ▲ system (virtual, non-cash)
- ✓ product ledger entry, value-only (qty 0, value −); product status unchanged (ACTIVE)

**Valuation / end_assets (no double count):**
- The loss is reflected **once** in movement-based inventory value (`capital_delta`) and **once** in `profit_loss` (cost) — the `end_assets` decrease equals the recognized loss.
- `CAPITAL_LOSS_PAYMENT` is non-cash — it never drains the entity's fund balance.

## reverse
**Validation:**
- Not already reversed
- Not a reversal
- Reason required (view-level)

**Success effects:**
- Reversal record created, linked via `reversal_of`
- Counter-transactions for issuance + payment (`system.fund → entity`)
- Negated product ledger entry; entity fund restored

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

**Scope (loss types):**
- `CAPITAL_LOSS` records a **value write-down only** — the asset (e.g. an animal) stays alive and in inventory: quantity is unchanged, no `InventoryMovementLine` is created, and product status is not changed to DEAD.
- Animal **death** is a separate operation (`DEATH`), which creates inventory movement lines to move the dead animal out of the project. `CAPITAL_LOSS` must never be used for a death.

Tasks:
- [x] Verify issuance and payment transactions are created
- [x] Verify transaction types are `CAPITAL_LOSS_ISSUANCE` and `CAPITAL_LOSS_PAYMENT`
- [x] Verify transaction funds: source=entity, target=system.fund
- [x] Verify destination is the System entity (`is_system=True`)
- [x] Verify non-system destination raises ValidationError
- [x] Verify source entity must be active
- [x] Verify source fund must be active
- [x] Verify source fund must NOT have sufficient balance, i.e:. loss project can further loss capitals.
- [x] Verify capital loss is value-only: ledger entry `quantity_delta=0` and no `InventoryMovementLine` is created
- [x] Verify product status stays active after a capital loss (not SOLD/DEAD)
- [x] Verify entity fund decreases by the loss amount
- [x] Verify operation is fully settled immediately after creation
- [x] Verify amount/officer validations (zero, negative, non-staff, inactive, no-user)
- [x] Verify source, destination, and amount are immutable after creation
- [x] Verify one-shot constraint prevents a second payment transaction
- [x] Verify reversal creates a reversal operation linked to the original
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify reversal counter-transactions flip funds (`system.fund → entity`)
- [x] Verify counter-transactions preserve transaction type
- [x] Verify entity fund is restored to pre-loss balance after reversal
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [ ] UI: create form — destination locked to System entity
- [ ] UI: operation detail shows issuance transaction and reversal button


