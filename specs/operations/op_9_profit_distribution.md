# Profit Distribution
**Epic:** 9.3 — Project Capital Operations
**Type:** One-shot, auto-settled
**Transaction flow:**
- Issuance: `project.fund → shareholder.fund` — type: `PROFIT_DISTRIBUTION_ISSUANCE`
- Payment: `project.fund → shareholder.fund` — type: `PROFIT_DISTRIBUTION_PAYMENT`

**Settlement:** Fully settled immediately — `is_fully_settled=True`, `amount_settled == amount`, `amount_remaining_to_settle == 0`

**Validation:**
- Source must be a Project entity
- Destination must be a Person (shareholder) entity
- Both entities must be `active=True`
- Source entity's fund must be `active=True`
- Source fund must have sufficient balance (`fund.balance >= amount`)
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

Tasks:
- [x] Verify both `PROFIT_DISTRIBUTION_ISSUANCE` and `PROFIT_DISTRIBUTION_PAYMENT` transactions are created on save
- [x] Verify transaction fund direction: `project.fund → shareholder.fund` for both
- [x] Verify operation is fully settled immediately
- [x] Verify source must be a Project entity
- [x] Verify destination must be a shareholder entity
- [x] Verify plan required
- [x] Verify plan must be a profit plan (loss plan raises)
- [x] Verify break-even plan raises
- [x] Verify amount must not exceed `plan.remaining_distributable`
- [x] Verify amount cap still enforced after partial distribution
- [x] Verify insufficient project fund balance raises ValidationError
- [x] Verify officer validations (non-staff raises)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `create_payment_transaction()` is blocked after creation (one-shot)
- [x] Verify reversal creates counter-transactions: `shareholder.fund → project.fund`
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify reversal is marked as `is_reversal`
- [x] Verify reversal inherits amount, source, destination from original
- [x] Verify counter-transactions preserve transaction type
- [x] Verify project fund restored after reversal
- [x] Verify reversal restores `remaining_distributable`
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [x] Verify project balance decreases after distribution
- [x] Verify shareholder balance increases after distribution
- [ ] UI: create form — source filtered to Project entities, destination filtered to Person entities
- [ ] UI: operation detail shows both transactions and reversal button
