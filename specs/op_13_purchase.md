# Purchase
**Epic:** 11.1 — Payable Operations
**Type:** Payable (`can_pay=True`, `is_partially_payable=True`, has invoice)
**Transaction flow:**
- Issuance: records liability — type: `PURCHASE_ISSUANCE` (no cash movement)
- Payment: `project.fund → vendor.fund` — type: `PURCHASE_PAYMENT`

**Validation:**
- Source must be a Project entity
- Destination must be a Vendor entity (`is_vendor=True`)
- Destination must be an active vendor of the source project (via Stakeholder)
- Both entities must be `active=True`
- Source entity's fund must be `active=True`
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

Tasks:
- [ ] Verify issuance transaction is created on save (type `PURCHASE_ISSUANCE`, records the purchase obligation)
- [ ] Verify source must be a Project entity (non-project source raises ValidationError)
- [ ] Verify destination must be a Vendor entity (non-vendor destination raises ValidationError)
- [ ] Verify both entities must be `active=True`
- [ ] Verify source fund must be `active=True`
- [ ] Verify amount/officer validations (zero, negative, non-staff, inactive, no-user)
- [ ] Verify immutability of `source`, `destination`, `amount` after save
- [ ] Fix payment view direction: `source=operation.source.fund` (project), `target=operation.destination.fund` (vendor) — see Epic 1 Feature 1.3
- [ ] Verify payment transaction deducts from project fund and credits vendor fund
- [ ] Verify partial payments are allowed (multiple payments up to total amount)
- [ ] Verify payment cannot exceed remaining amount (`amount_remaining_to_settle`)
- [ ] Verify invoice line items are optional but validated if present
- [ ] Reversal: reverses the issuance and all payment transactions
- [ ] Verify reversal marks original as reversed and sets `reversed_by`
- [ ] Verify cannot reverse an already-reversed operation
- [ ] UI: create form — source=Project, destination=Vendor, optional invoice formset
- [ ] UI: detail shows total amount, paid so far, remaining; "Record Payment" button
