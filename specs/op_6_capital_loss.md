# Capital Loss
**Epic:** 10.3 — Miscellaneous One-Shot Operations
**Type:** One-shot
**Transaction flow:**
- Issuance: `entity → system.fund` — type: `CAPITAL_LOSS_ISSUANCE`
- Payment: `entity → system.fund` — type: `CAPITAL_LOSS_PAYMENT`

**Settlement:** Fully settled immediately — `is_fully_settled=True`, `amount_settled == amount`, `amount_remaining_to_settle == 0`

**Validation:**
- Destination must be the System entity (`is_system=True`)
- Source entity must be `active=True`
- Source entity's fund must be `active=True`
- Source fund must have sufficient balance (`fund.balance >= amount`)
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

Tasks:
- [x] Verify issuance and payment transactions are created
- [x] Verify transaction types are `CAPITAL_LOSS_ISSUANCE` and `CAPITAL_LOSS_PAYMENT`
- [x] Verify transaction funds: source=entity, target=system.fund
- [x] Verify destination is the System entity (`is_system=True`)
- [x] Verify non-system destination raises ValidationError
- [x] Verify source entity must be active
- [x] Verify source fund must be active
- [ ] Verify source fund must have sufficient balance (insufficient funds raises ValidationError)
- [x] Verify entity fund decreases by the loss amount
- [x] Verify operation is fully settled immediately after creation
- [x] Verify amount/officer validations (zero, negative, non-staff, inactive, no-user)
- [x] Verify source, destination, and amount are immutable after creation
- [x] Verify one-shot constraint prevents a second payment transaction
- [x] Verify reversal creates a reversal operation linked to the original
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify reversal counter-transactions flip funds (`system.fund → entity`)
- [x] Verify counter-transactions preserve transaction type
- [x] Verify entity fund is restored to pre-loss balance after reversal
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [ ] UI: create form — destination locked to System entity
- [ ] UI: operation detail shows issuance transaction and reversal button
