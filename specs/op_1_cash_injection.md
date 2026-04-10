# Cash Injection
**Epic:** 8.1 — Cash Operations
**Type:** One-shot, auto-settled
**Transaction flow:**
- Issuance: `world.fund → person.fund` — type: `CASH_INJECTION_ISSUANCE`
- Payment: `world.fund → person.fund` — type: `CASH_INJECTION_PAYMENT`

**Settlement:** Fully settled immediately — `is_fully_settled=True`, `amount_settled == amount`, `amount_remaining_to_settle == 0`

**Validation:**
- Source must be the World entity (`is_world=True`)
- Destination must be a Person entity
- Both entities must be `active=True`
- Source entity's fund must be `active=True`
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

Tasks:
- [x] Verify both `CASH_INJECTION_ISSUANCE` and `CASH_INJECTION_PAYMENT` transactions are created on save
- [x] Verify transaction fund direction: `world.fund → person.fund` for both
- [x] Verify operation is fully settled immediately
- [x] Verify all validation rules listed above
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `create_payment_transaction()` is blocked after creation
- [x] Verify reversal creates counter-transactions: `person.fund → world.fund`
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify counter-transactions preserve transaction type
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [ ] UI: create form — source locked to World entity, destination filtered to Person entities
- [ ] UI: operation detail shows both transactions and reversal button
