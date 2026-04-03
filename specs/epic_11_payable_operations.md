# EPIC 11 — Payable Operations
> Operations that record an obligation on creation and accept one or more payments later.

---

### Feature 11.1 — Purchase
**Type:** Payable (`can_pay=True`, `is_partially_payable=True`, has invoice)
**Transaction flow:**
- Issuance: records liability — type: `PURCHASE_ISSUANCE` (no cash movement)
- Payment: `project.fund → vendor.fund` — type: `PURCHASE_PAYMENT`

Tasks:
- [ ] Verify issuance transaction is created on save (records the purchase obligation)
- [ ] Fix payment view direction: `source=operation.source.fund` (project), `target=operation.destination.fund` (vendor) — see Epic 1 Feature 1.3
- [ ] Verify partial payments are allowed (multiple payments up to total amount)
- [ ] UI: create form — source=Project, destination=Vendor, optional invoice formset
- [ ] UI: detail shows total amount, paid so far, remaining; "Record Payment" button
- [ ] Reversal: reverses the issuance and all payment transactions

---

### Feature 11.2 — Sale
**Type:** Payable (`can_pay=True`, `is_partially_payable=True`, has invoice)
**Transaction flow:**
- Issuance: records receivable — type: `SALE_ISSUANCE` (no cash movement)
- Collection: `client.fund → project.fund` — type: `SALE_COLLECTION`

Tasks:
- [ ] Verify issuance transaction created on save
- [ ] Fix payment view direction: `source=operation.source.fund` (client), `target=operation.destination.fund` (project) — see Epic 1 Feature 1.3
- [ ] Verify partial collections are allowed
- [ ] UI: create form — source=Client, destination=Project, optional invoice formset
- [ ] UI: detail shows total amount, collected so far, remaining; "Record Collection" button
- [ ] Reversal: reverses issuance and all collection transactions

---

### Feature 11.3 — Expense
**Type:** Payable (`can_pay=True`, `is_partially_payable=True`, category required)
**Transaction flow:**
- Issuance: records expense obligation — type: `EXPENSE_ISSUANCE`
- Payment: `project.fund → world.fund` — type: `EXPENSE_PAYMENT`

Tasks:
- [ ] Verify issuance transaction created on save
- [ ] Fix payment view direction: `source=operation.source.fund` (project), `target=operation.destination.fund` (world) — see Epic 1 Feature 1.3
- [ ] Verify category is required and saved correctly
- [ ] UI: create form — source=Project, destination=World, category dropdown (required)
- [ ] UI: detail shows category, amount paid, remaining; "Record Payment" button
- [ ] Reversal: reverses issuance and all payment transactions
