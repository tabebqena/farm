# Loss Coverage
**Epic:** 9.4 — Project Capital Operations
**Type:** One-shot, auto-settled
**Transaction flow:**
- Issuance: `shareholder.fund → project.fund` — type: `LOSS_COVERAGE_ISSUANCE`
- Payment: `shareholder.fund → project.fund` — type: `LOSS_COVERAGE_PAYMENT`

**Settlement:** Fully settled immediately — `is_fully_settled=True`, `amount_settled == amount`, `amount_remaining_to_settle == 0`

**Validation:**
- Source must be a Person (shareholder) entity
- Destination must be a Project entity
- Both entities must be `active=True`
- Source entity's fund must be `active=True`
- Source fund must have sufficient balance (`fund.balance >= amount`)
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

Tasks:
- [ ] Verify both `LOSS_COVERAGE_ISSUANCE` and `LOSS_COVERAGE_PAYMENT` transactions are created on save
- [ ] Verify transaction fund direction: `shareholder.fund → project.fund` for both
- [ ] Verify operation is fully settled immediately
- [ ] Verify all validation rules listed above (including insufficient funds check)
- [ ] Verify immutability of `source`, `destination`, `amount` after save
- [ ] Verify `create_payment_transaction()` is blocked after creation
- [ ] Verify reversal creates counter-transactions: `project.fund → shareholder.fund`
- [ ] Verify reversal marks original as reversed and sets `reversed_by`
- [ ] Verify counter-transactions preserve transaction type
- [ ] Verify cannot reverse an already-reversed operation
- [ ] Verify cannot reverse a reversal operation
- [ ] Verify shareholder balance decreases after loss coverage
- [ ] Verify shareholder balance restored after reversal
- [ ] UI: create form — source filtered to Person entities, destination filtered to Project entities
- [ ] UI: operation detail shows both transactions and reversal button
