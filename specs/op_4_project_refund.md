# Project Refund
**Epic:** 9.2 — Project Capital Operations
**Type:** One-shot, auto-settled
**Transaction flow:**
- Issuance: `project.fund → person.fund` — type: `PROJECT_REFUND_ISSUANCE`
- Payment: `project.fund → person.fund` — type: `PROJECT_REFUND_PAYMENT`

**Settlement:** Fully settled immediately — `is_fully_settled=True`, `amount_settled == amount`, `amount_remaining_to_settle == 0`

**Validation:**
- Source must be a Project entity
- Destination must be a Person entity
- Destination must be a registered active shareholder of the source project
- Both entities must be `active=True`
- Source entity's fund must be `active=True`
- Source fund must have sufficient balance (`fund.balance >= amount`)
- Refund amount must not exceed the net amount funded by the shareholder into this project
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

Tasks:
- [x] Verify both `PROJECT_REFUND_ISSUANCE` and `PROJECT_REFUND_PAYMENT` transactions are created on save
- [x] Verify transaction fund direction: `project.fund → person.fund` for both
- [x] Verify operation is fully settled immediately
- [x] Verify all validation rules listed above (including insufficient funds check)
- [x] Verify destination must be a registered shareholder of the source project
- [x] Verify refund amount cannot exceed shareholder's net funded amount (cumulative cap across multiple refunds)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `create_payment_transaction()` is blocked after creation
- [x] Verify reversal creates counter-transactions: `person.fund → project.fund`
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify counter-transactions preserve transaction type
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [x] Verify project balance decreases after refund
- [x] Verify project balance restored after reversal
- [x] Verify shareholder balance increases after refund
- [x] Verify shareholder balance restored after reversal
- [ ] UI: create form — source filtered to Project entities, destination filtered to Person entities
- [ ] UI: operation detail shows both transactions and reversal button
