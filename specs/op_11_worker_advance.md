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
- [ ] Verify issuance transaction created correctly (project → worker, type `WORKER_ADVANCE_ISSUANCE`)
- [ ] Verify source must be a Project entity (non-project source raises ValidationError)
- [ ] Verify destination must be a Person entity (non-person destination raises ValidationError)
- [ ] Verify destination must be an active Worker in the source project (non-worker raises ValidationError)
- [ ] Verify both entities must be `active=True`
- [ ] Verify source fund must be `active=True`
- [ ] Verify source fund must have sufficient balance (insufficient funds raises ValidationError)
- [ ] Verify amount/officer validations (zero, negative, non-staff, inactive, no-user)
- [ ] Verify immutability of `source`, `destination`, `amount` after save
- [ ] Verify `create_payment_transaction()` is blocked after creation (one-shot)
- [ ] Verify repayment view creates transaction in correct direction: `destination.fund → source.fund` (worker → project)
- [ ] Verify repayment transaction type is `WORKER_ADVANCE_REPAYMENT`
- [ ] Verify `amount_remaining_to_repay` property: `issuance_amount - sum(repayments)`
- [ ] Verify repayment cannot exceed remaining balance (over-repayment raises error)
- [ ] Verify project fund decreases after advance
- [ ] Verify worker fund increases after advance
- [ ] Verify worker fund decreases after repayment
- [ ] Verify project fund increases after repayment
- [ ] Reversal: only if no outstanding repayments exist
- [ ] Verify reversal blocked if outstanding repayments exist
- [ ] Verify reversal marks original as reversed and sets `reversed_by`
- [ ] Verify cannot reverse an already-reversed operation
- [ ] UI: create form — source=Project, destination filtered to active workers of that project
- [ ] UI: detail shows advance amount, repaid so far, outstanding; "Record Repayment" button
- [ ] UI: repayment button blocks over-repayment (cannot repay more than advanced)
