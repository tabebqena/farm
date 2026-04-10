# Expense
**Epic:** 11.3 — Payable Operations
**Type:** Payable (`can_pay=True`, `is_partially_payable=True`, category required)
**Transaction flow:**
- Issuance: records expense obligation — type: `EXPENSE_ISSUANCE` (no cash movement)
- Payment: `project.fund → world.fund` — type: `EXPENSE_PAYMENT`

**Validation:**
- Source must be a Project entity
- Destination must be the World entity (`is_world=True`)
- Both entities must be `active=True`
- Source entity's fund must be `active=True`
- Category is required
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

Tasks:
- [ ] Verify issuance transaction created on save (type `EXPENSE_ISSUANCE`, no cash movement)
- [ ] Verify source must be a Project entity (non-project source raises ValidationError)
- [ ] Verify destination must be the World entity (non-world destination raises ValidationError)
- [ ] Verify both entities must be `active=True`
- [ ] Verify source fund must be `active=True`
- [ ] Verify category is required and saved correctly
- [ ] Verify amount/officer validations (zero, negative, non-staff, inactive, no-user)
- [ ] Verify immutability of `source`, `destination`, `amount` after save
- [ ] Fix payment view direction: `source=operation.source.fund` (project), `target=operation.destination.fund` (world) — see Epic 1 Feature 1.3
- [ ] Verify payment transaction deducts from project fund and credits world fund
- [ ] Verify partial payments are allowed (multiple payments up to total amount)
- [ ] Verify payment cannot exceed remaining amount (`amount_remaining_to_settle`)
- [ ] Reversal: reverses issuance and all payment transactions
- [ ] Verify reversal marks original as reversed and sets `reversed_by`
- [ ] Verify cannot reverse an already-reversed operation
- [ ] UI: create form — source=Project, destination=World, category dropdown (required)
- [ ] UI: detail shows category, amount paid, remaining; "Record Payment" button
