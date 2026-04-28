# Cash Withdrawal
**Epic:** 8.2 — Cash Operations
**Type:** One-shot, auto-settled
**Transaction flow:**
- Issuance: `person.fund → world.fund` — type: `CAPITAL_WITHDRAWAL_ISSUANCE`
- Payment: `person.fund → world.fund` — type: `CAPITAL_WITHDRAWAL_PAYMENT`

**Settlement:** Fully settled immediately — `is_fully_settled=True`, `amount_settled == amount`, `amount_remaining_to_settle == 0`

**Validation:**
- Source must be a Person entity
- Destination must be the World entity (`is_world=True`)
- Both entities must be `active=True`
- Source entity's fund must be `active=True`
- Source fund must have sufficient balance (`fund.balance >= amount`)
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

Tasks:
- [x] Verify both `CAPITAL_WITHDRAWAL_ISSUANCE` and `CAPITAL_WITHDRAWAL_PAYMENT` transactions are created on save
- [x] Verify transaction fund direction: `person.fund → world.fund` for both
- [x] Verify operation is fully settled immediately
- [x] Verify all validation rules listed above (including insufficient funds check)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `create_payment_transaction()` is blocked after creation
- [x] Verify reversal creates counter-transactions: `world.fund → person.fund`
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify counter-transactions preserve transaction type
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [x] Verify withdrawer balance decreases after withdrawal
- [x] Verify withdrawer balance restored after reversal
- [ ] UI: create form — source filtered to Person entities, destination locked to World entity
- [ ] UI: operation detail shows both transactions and reversal button
