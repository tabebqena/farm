# Worker Advance
**Epic:** 12.2 — Repayable Operations
**Type:** One-shot issuance + has repayment
**Transaction flow:**
- Issuance: `project.fund → worker.fund` — type: `WORKER_ADVANCE_ISSUANCE`
- Payment: `project.fund → worker.fund` — type: `WORKER_ADVANCE_PAYMENT`
- Repayment (recovery): `worker.fund → project.fund` — type: `WORKER_ADVANCE_REPAYMENT`

**Validation:**
- Source must be a Project entity
- Destination must be a Person entity
- Destination must be an active Worker (Stakeholder with `role=WORKER`) of the source project
- Both entities must be `active=True`
- Source entity's fund must be `active=True`
- Source fund must have sufficient balance (`fund.balance >= amount`)
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

Tasks:

**Validation**
- [ ] Verify source must be a Project entity (non-project source raises ValidationError)
- [ ] Verify destination must be a Person entity (non-person destination raises ValidationError)
- [ ] Verify destination must be an active Worker (Stakeholder with `role=WORKER`) in the source project (non-worker raises ValidationError)
- [ ] Verify both entities must be `active=True` (inactive source or destination raises ValidationError)
- [ ] Verify source fund must be `active=True` (inactive fund raises ValidationError)
- [ ] Verify source fund must have sufficient balance (insufficient funds raises ValidationError)
- [ ] Verify amount must be positive (zero and negative amounts raise ValidationError)
- [ ] Verify officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True` (non-staff, inactive, no-user raise ValidationError)
- [ ] Verify immutability of `source`, `destination`, `amount` after save

**One-Shot Issuance (project → worker)**
- [ ] Verify both issuance and payment transactions are created together at operation creation (one-shot — no separate call required)
- [ ] Verify issuance transaction direction: `project.fund → worker.fund`, type `WORKER_ADVANCE_ISSUANCE`
- [ ] Verify payment transaction direction: `project.fund → worker.fund`, type `WORKER_ADVANCE_PAYMENT`
- [ ] Verify no additional project → worker transactions can be created after the initial one-shot pair
- [ ] Verify project fund balance decreases by the advance amount after creation
- [ ] Verify worker fund balance increases by the advance amount after creation

**Repayment (worker → project)**
- [ ] Verify repayment transaction direction: `worker.fund → project.fund`, type `WORKER_ADVANCE_REPAYMENT`
- [ ] Verify multiple repayments are allowed (partial repayments over time)
- [ ] Verify `amount_remaining_to_repay` property: `advance_amount - sum(repayments)`
- [ ] Verify repayment cannot exceed `amount_remaining_to_repay` (over-repayment raises ValidationError)
- [ ] Verify worker fund balance decreases after repayment
- [ ] Verify project fund balance increases after repayment
- [ ] Verify `amount_remaining_to_repay` reaches zero after full repayment

**Reversal**
- [ ] Verify reversal is blocked if any repayments exist
- [ ] Verify reversal is allowed when no repayments have been made
- [ ] Verify reversal marks the operation as reversed and sets `reversed_by`
- [ ] Verify cannot reverse an already-reversed operation

**UI**
- [ ] UI: create form — source restricted to Projects, destination filtered to active workers of the selected project
- [ ] UI: detail view shows advance amount, total repaid so far, outstanding balance, and "Record Repayment" button
- [ ] UI: repayment form pre-fills max allowed amount and blocks submission if repayment exceeds outstanding balance
