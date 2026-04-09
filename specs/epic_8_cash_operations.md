# EPIC 8 — Cash Operations
> World-entity capital entry and exit points.

---

### Feature 8.1 — Cash Injection
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
- [ ] Verify reversal creates counter-transactions: `person.fund → world.fund`
- [ ] UI: create form — source locked to World entity, destination filtered to Person entities
- [ ] UI: operation detail shows both transactions and reversal button

---

### Feature 8.2 — Cash Withdrawal
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
- [x] Verify withdrawer balance decreases after withdrawal
- [x] Verify withdrawer balance restored after reversal
- [ ] UI: create form — source filtered to Person entities, destination locked to World entity
- [ ] UI: operation detail shows both transactions and reversal button
