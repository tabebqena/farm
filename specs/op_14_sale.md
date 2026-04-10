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
- [ ] Verify issuance transaction created on save (type `SALE_ISSUANCE`, records receivable)
- [ ] Verify source must be a Client entity (non-client source raises ValidationError)
- [ ] Verify destination must be a Project entity (non-project destination raises ValidationError)
- [ ] Verify both entities must be `active=True`
- [ ] Verify source fund must be `active=True`
- [ ] Verify amount/officer validations (zero, negative, non-staff, inactive, no-user)
- [ ] Verify immutability of `source`, `destination`, `amount` after save
- [ ] Fix collection view direction: `source=operation.source.fund` (client), `target=operation.destination.fund` (project) — see Epic 1 Feature 1.3
- [ ] Verify collection transaction deducts from client fund and credits project fund
- [ ] Verify partial collections are allowed (multiple collections up to total amount)
- [ ] Verify collection cannot exceed remaining amount (`amount_remaining_to_settle`)
- [ ] Reversal: reverses issuance and all collection transactions
- [ ] Verify reversal marks original as reversed and sets `reversed_by`
- [ ] Verify cannot reverse an already-reversed operation
- [ ] UI: create form — source=Client, destination=Project, optional invoice formset
- [ ] UI: detail shows total amount, collected so far, remaining; "Record Collection" button
