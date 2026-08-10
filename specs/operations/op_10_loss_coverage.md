# Loss Coverage
**Epic:** 9.4 — Project Capital Operations
**Type:** One-shot, auto-settled
**Transaction flow:**
- Issuance: `shareholder.fund → project.fund` — type: `LOSS_COVERAGE_ISSUANCE`
- Payment: `shareholder.fund → project.fund` — type: `LOSS_COVERAGE_PAYMENT`

**Settlement:** Fully settled immediately — `is_fully_settled=True`, `amount_settled == amount`, `amount_remaining_to_settle == 0`

**Actions:** create, reverse.

## create
**Validation:**
- Source must be a Person (shareholder) entity — enforced via `clean_source()` (`is_shareholder=True`)
- Destination must be a Project entity — enforced via `clean_destination()` (`is_project=True`)
- Both entities must be `active=True`
- Source entity's fund must be `active=True`
- Source fund must have sufficient balance (`fund.balance >= amount`)
- Plan required; plan must be a **loss** plan (profit / break-even reject)
- Amount must not exceed `plan.remaining_coverable` (cumulative cap across partial coverage)
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`
- One-shot auto-settled — payment transaction fires on save (`E@create` pay)

**Success effects:**
- `LOSS_COVERAGE_ISSUANCE` + `LOSS_COVERAGE_PAYMENT` created on save
- Immediately settled (`is_fully_settled=True`)
- Fund deltas: ▼ shareholder → ▲ project
- Plan tracking: `covered` ↑ / `remaining_coverable` ↓

## reverse
**Validation:**
- Not already reversed / not a reversal / reason required

**Success effects:**
- Reversal record; counter-transactions for issuance + payment
- Restores `remaining_coverable`

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

Tasks:
- [x] Verify source must be a Person shareholder entity (`clean_source`) — non-shareholder raises
- [x] Verify destination must be a Project entity (`clean_destination`) — non-project raises
- [x] Verify both `LOSS_COVERAGE_ISSUANCE` and `LOSS_COVERAGE_PAYMENT` transactions are created on save
- [x] Verify transaction fund direction: `shareholder.fund → project.fund` for both
- [x] Verify operation is fully settled immediately
- [x] Verify plan required
- [x] Verify plan must be a loss plan (profit plan raises)
- [x] Verify break-even plan raises
- [x] Verify amount must not exceed `plan.remaining_coverable`
- [x] Verify amount cap still enforced after partial coverage
- [x] Verify insufficient shareholder fund balance raises ValidationError
- [x] Verify officer validations (non-staff raises)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `create_payment_transaction()` is blocked after creation (one-shot)
- [x] Verify reversal creates counter-transactions: `project.fund → shareholder.fund`
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify reversal is marked as `is_reversal`
- [x] Verify reversal inherits amount, source, destination from original
- [x] Verify counter-transactions preserve transaction type
- [x] Verify shareholder fund restored after reversal
- [x] Verify reversal restores `remaining_coverable`
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [x] Verify shareholder balance decreases after loss coverage
- [x] Verify project balance increases after loss coverage
- [ ] UI: create form — source filtered to Person entities, destination filtered to Project entities
- [ ] UI: operation detail shows both transactions and reversal button
