# Capital Gain
**Epic:** 10.2 — Miscellaneous One-Shot Operations
**Type:** One-shot
**Transaction flow:**
- Issuance: `system.fund → entity` — type: `CAPITAL_GAIN_ISSUANCE`
- Payment: `system.fund → entity` — type: `CAPITAL_GAIN_PAYMENT` — **non-cash bookkeeping** (excluded from `payment_types()`; the payment never affects the project's fund balance)

**Actions:** create, reverse.

## create
**Validation:**
- Source must be the System entity (`is_system=True`) — enforced via `clean_source()`
- Destination must be a Project entity (`is_project=True`) — enforced via `clean_destination()`; must be `active=True`
- Both entities' funds `active=True`
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`
- Balance @ create: **exempt** (system payer) — `E@create` pay (one-shot)

**Success effects:**
- `CAPITAL_GAIN_ISSUANCE` + `CAPITAL_GAIN_PAYMENT` created on save
- Immediately settled (`is_fully_settled=True`)
- Fund deltas: **no cash flow** — ▼ system (virtual, non-cash) → ▲ project (inventory value only)
- ✓ product ledger entry, value-only (qty 0, value +); product status unchanged (ACTIVE)

**Valuation / end_assets (no double count):**
- The gain is reflected **once** in movement-based inventory value (`capital_delta`) and **once** in `profit_loss` (income) — the `end_assets` increase equals the recognized gain.
- `CAPITAL_GAIN_PAYMENT` is non-cash — it never inflates the project's fund balance.

## reverse
**Validation:**
- Not already reversed
- Not a reversal
- Reason required (view-level)

**Success effects:**
- Reversal record created, linked via `reversal_of`
- Counter-transactions for issuance + payment (`project.fund → system.fund`)
- Negated product ledger entry; project fund restored

Tasks:
- [x] Verify issuance and payment transactions are created
- [x] Verify transaction types are `CAPITAL_GAIN_ISSUANCE` and `CAPITAL_GAIN_PAYMENT`
- [x] Verify transaction funds: source=system.fund, target=project.fund
- [x] Verify source is the System entity (`is_system=True`)
- [x] Verify non-system source (person or world entity) raises ValidationError
- [x] Verify destination is a project entity and must be active
- [x] Verify project fund increases by the gain amount
- [x] Verify operation is fully settled immediately after creation
- [x] Verify amount/officer validations (zero, negative, non-staff, inactive, no-user)
- [x] Verify source, destination, and amount are immutable after creation
- [x] Verify one-shot constraint prevents a second payment transaction
- [x] Verify reversal creates a reversal operation linked to the original
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify reversal counter-transactions flip funds (project.fund → system.fund)
- [x] Verify counter-transactions preserve transaction type
- [x] Verify project fund is restored to pre-gain balance after reversal
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [ ] UI: create form — source locked to System entity
- [ ] UI: operation detail shows issuance transaction and reversal button
