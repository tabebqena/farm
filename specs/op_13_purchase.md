# Purchase
**Epic:** 11.1 — Payable Operations
**Type:** Payable (`can_pay=True`, `is_partially_payable=True`, has invoice)

**Concept:** Records an obligation to pay a registered vendor for a product. Creating the operation records the liability once (issuance). The project then pays the vendor in one or multiple installments. The project fund balance changes only on payment, not on issuance.

**Transaction flow:**
- Issuance: records purchase liability — type: `PURCHASE_ISSUANCE` (non-cash, does NOT affect fund balances)
- Payment: `project.fund → vendor.fund` — type: `PURCHASE_PAYMENT` (cash movement, deducts from project fund)
- Only one issuance transaction is ever created (on save). No further issuance transactions are allowed.
- Payments can be made in multiple partial installments up to the total amount.

**Entities:**
- Source: a Project entity (`source.project` must be set)
- Destination: a Vendor entity (`destination.is_vendor=True`), must be an active vendor of the source project (via Stakeholder)

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
- [ ] Verify save creates only one PURCHASE_ISSUANCE transaction (not payment — not one-shot)
- [ ] Verify no PURCHASE_PAYMENT transaction is created on save
- [ ] Verify PURCHASE_ISSUANCE direction: source=project.fund, target=vendor.fund
- [ ] Verify PURCHASE_ISSUANCE is non-cash: project fund balance unchanged after save
- [ ] Verify amount_remaining_to_settle equals full amount after creation
- [ ] Verify is_not_fully_settled after creation
- [ ] Verify source must be a Project entity (non-project source raises ValidationError)
- [ ] Verify source must be active (inactive source raises ValidationError)
- [ ] Verify source fund must be active
- [ ] Verify destination must be a Vendor entity (non-vendor destination raises ValidationError)
- [ ] Verify destination must be an active vendor of the source project (non-stakeholder vendor raises ValidationError)
- [ ] Verify amount/officer validations (zero, negative, non-staff, inactive, no-user)
- [ ] Verify immutability of `source`, `destination`, `amount` after save
- [ ] Verify payment creates PURCHASE_PAYMENT transaction (direction: project.fund → vendor.fund)
- [ ] Verify payment amount_remaining_to_settle decreases correctly
- [ ] Verify multiple partial payments are allowed and accumulate
- [ ] Verify full payment marks operation as fully settled
- [ ] Verify project fund decreases by payment amount (PURCHASE_PAYMENT is cash)
- [ ] Verify vendor fund increases by payment amount
- [ ] Verify payment cannot exceed remaining amount (over-payment raises ValidationError)
- [ ] Verify zero/negative payment raises ValidationError
- [ ] Reversal: reverses issuance counter-transaction only (payment transactions block reversal)
- [ ] Verify reversal creates reversal operation with correct linkage
- [ ] Verify reversal marks original as reversed
- [ ] Verify reversal is marked as is_reversal
- [ ] Verify reversal inherits amount, source, destination from original
- [ ] Verify reversal creates exactly 1 counter-transaction (for issuance only)
- [ ] Verify reversal counter-transaction flips source/target funds
- [ ] Verify project fund unchanged after reversal (issuance is non-cash)
- [ ] Verify reversal is blocked when any PURCHASE_PAYMENT transaction exists
- [ ] Verify cannot reverse an already-reversed operation
- [ ] Verify cannot reverse a reversal operation
- [ ] UI: create form — source=Project (url entity), destination=Vendor (from stakeholders), optional invoice formset
- [ ] UI: detail shows total amount, paid so far, remaining; "Record Payment" button
