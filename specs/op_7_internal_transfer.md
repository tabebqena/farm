# Internal Transfer
**Epic:** 10.1 — Miscellaneous One-Shot Operations
**Type:** One-shot (both entities must be internal)
**Transaction flow:**
- Issuance: `source.fund → destination.fund` — type: `INTERNAL_TRANSFER_ISSUANCE`
- Payment: `source.fund → destination.fund` — type: `INTERNAL_TRANSFER_PAYMENT`

**Settlement:** Fully settled immediately — `is_fully_settled=True`, `amount_settled == amount`, `amount_remaining_to_settle == 0`

**Validation:**
- Source must be an internal entity (`is_internal=True`)
- Destination must be an internal entity (`is_internal=True`)
- Neither source nor destination may be a system or world entity
- Both entities must be `active=True`
- Source entity's fund must be `active=True`
- Source fund must have sufficient balance (`fund.balance >= amount`)
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

Tasks:
- [x] Verify both `INTERNAL_TRANSFER_ISSUANCE` and `INTERNAL_TRANSFER_PAYMENT` transactions are created on save
- [x] Verify transaction fund direction: `source.fund → destination.fund` for both
- [x] Verify operation is fully settled immediately
- [x] Verify source must be an internal entity (`is_internal=True`)
- [x] Verify non-internal source raises ValidationError
- [x] Verify destination must be an internal entity (`is_internal=True`)
- [x] Verify non-internal destination raises ValidationError
- [x] Verify system entity as source raises ValidationError
- [x] Verify system entity as destination raises ValidationError
- [x] Verify world entity as source raises ValidationError
- [x] Verify world entity as destination raises ValidationError
- [x] Verify both entities must be `active=True`
- [x] Verify source fund must be `active=True`
- [x] Verify source fund must have sufficient balance (insufficient funds raises ValidationError)
- [x] Verify amount/officer validations (zero, negative, non-staff, inactive, no-user)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `create_payment_transaction()` is blocked after creation
- [x] Verify reversal creates counter-transactions: `destination.fund → source.fund`
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify counter-transactions preserve transaction type
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [x] Verify source balance decreases after transfer
- [x] Verify destination balance increases after transfer
- [x] Verify source balance restored after reversal
- [x] Verify destination balance restored after reversal
- [ ] UI: create form — entity dropdowns filtered to internal entities only
- [ ] UI: operation detail shows both transactions and reversal button
