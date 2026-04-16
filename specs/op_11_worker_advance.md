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
- [x] Verify source must be a Project entity (non-project source raises ValidationError)
- [x] Verify destination must be a Person entity (non-person destination raises ValidationError)
- [x] Verify destination must be an active Worker (Stakeholder with `role=WORKER`) in the source project (non-worker raises ValidationError)
- [x] Verify destination without stakeholder relationship raises ValidationError
- [x] Verify destination with inactive stakeholder raises ValidationError
- [x] Verify both entities must be `active=True` (inactive source or destination raises ValidationError)
- [x] Verify source fund must be `active=True` (inactive fund raises ValidationError)
- [x] Verify source fund must have sufficient balance (insufficient funds raises ValidationError)
- [x] Verify amount must be positive (zero and negative amounts raise ValidationError)
- [x] Verify officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True` (non-staff, inactive raise ValidationError)
- [x] Verify immutability of `source`, `destination`, `amount` after save

**One-Shot Issuance (project → worker)**
- [x] Verify both issuance and payment transactions are created together at operation creation
- [x] Verify issuance transaction direction: `project.fund → worker.fund`, type `WORKER_ADVANCE_ISSUANCE`
- [x] Verify payment transaction direction: `project.fund → worker.fund`, type `WORKER_ADVANCE_PAYMENT`
- [x] Verify no additional project → worker transactions can be created after the initial one-shot pair
- [x] Verify project fund balance decreases by the advance amount after creation
- [x] Verify worker fund balance increases by the advance amount after creation
- [x] Verify `amount_remaining_to_repay` equals full amount after creation

**Repayment (worker → project)**
- [x] Verify repayment transaction direction: `worker.fund → project.fund`, type `WORKER_ADVANCE_REPAYMENT`
- [x] Verify multiple repayments are allowed (partial repayments over time)
- [x] Verify `amount_remaining_to_repay` property decreases after repayment
- [x] Verify repayment cannot exceed `amount_remaining_to_repay` (over-repayment raises ValidationError)
- [x] Verify partial repayment then over-repayment raises ValidationError
- [x] Verify zero repayment raises ValidationError
- [x] Verify worker fund balance decreases after repayment
- [x] Verify project fund balance increases after repayment
- [x] Verify `amount_remaining_to_repay` reaches zero after full repayment

**Reversal**
- [x] Verify reversal is blocked if any repayments exist
- [x] Verify reversal creates counter-transactions for both issuance and payment
- [x] Verify reversal counter-transactions flip funds
- [x] Verify project fund restored after reversal
- [x] Verify worker fund restored after reversal
- [x] Verify reversal marks the operation as reversed and sets `reversed_by`
- [x] Verify reversal is marked as `is_reversal`
- [x] Verify reversal inherits amount, source, destination from original
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation

**UI**
- [ ] UI: create form — source restricted to Projects, destination filtered to active workers of the selected project
- [ ] UI: detail view shows advance amount, total repaid so far, outstanding balance, and "Record Repayment" button
- [ ] UI: repayment form pre-fills max allowed amount and blocks submission if repayment exceeds outstanding balance
