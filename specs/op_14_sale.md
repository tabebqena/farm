# Sale
**Epic:** 11.2 — Payable Operations
**Type:** Payable (`can_pay=True`, `is_partially_payable=True`, has invoice)
**Transaction flow:**
- Issuance: records receivable — type: `SALE_ISSUANCE` (no cash movement)
- Collection: `client.fund → project.fund` — type: `SALE_COLLECTION`

**Validation:**
- Source must be a Client entity (`is_client=True`)
- Source must be an active client of the destination project (via Stakeholder)
- Destination must be a Project entity
- Both entities must be `active=True`
- Source entity's fund must be `active=True`
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

Tasks:
- [x] Verify save creates only one SALE_ISSUANCE transaction (no collection on save)
- [x] Verify SALE_ISSUANCE direction: source=client.fund, target=project.fund (non-cash)
- [x] Verify project fund balance unchanged after save (issuance is non-cash)
- [x] Verify client fund balance unchanged after save
- [x] Verify amount_remaining_to_settle equals full amount after creation
- [x] Verify is_not_fully_settled after creation
- [x] Verify source must be a Client entity (non-client source raises ValidationError)
- [x] Verify project entity as source raises ValidationError
- [x] Verify source must be active
- [x] Verify source fund must be `active=True`
- [x] Verify destination must be a Project entity
- [x] Verify destination must be an active client stakeholder (inactive stakeholder raises ValidationError)
- [x] Verify amount/officer validations (zero, negative, non-staff, inactive)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify collection creates SALE_COLLECTION transaction (direction: client.fund → project.fund)
- [x] Verify collection amount_remaining_to_settle decreases correctly
- [x] Verify multiple partial collections are allowed and accumulate
- [x] Verify full collection marks operation as fully settled
- [x] Verify client fund decreases by collection amount
- [x] Verify project fund increases by collection amount
- [x] Verify collection cannot exceed remaining amount (over-collection raises ValidationError)
- [x] Verify partial then over-collection raises ValidationError
- [x] Verify zero/negative collection raises ValidationError
- [x] Verify balance enforced on collection (insufficient client fund raises ValidationError)
- [x] Reversal creates reversal operation with correct linkage
- [x] Verify reversal marks original as reversed
- [x] Verify reversal is marked as is_reversal
- [x] Verify reversal inherits amount, source, destination from original
- [x] Verify reversal creates counter-transaction for issuance only
- [x] Verify reversal counter-transaction flips funds
- [x] Verify fund balances unchanged after reversal (issuance is non-cash)
- [x] Verify reversal is blocked when any SALE_COLLECTION transaction exists
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [ ] UI: create form — source=Client, destination=Project, optional invoice formset
- [ ] UI: detail shows total amount, collected so far, remaining; "Record Collection" button
