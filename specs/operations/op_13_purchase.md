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

**Actions:** create, pay, move items, adjust items, adjust, reverse.

## create
**Validation:**
- Source must be a Project entity
- Destination must be a Vendor entity (`is_vendor=True`)
- Destination must be an active vendor of the source project (via Stakeholder)
- Both entities must be `active=True`
- Source entity's fund must be `active=True`
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`
- Balance @ create: **exempt** (issuance unguarded); not one-shot

**Success effects:**
- `PURCHASE_ISSUANCE` created on save (non-cash obligation)
- No payment on save — payments happen later via **pay**
- ✓ product ledger issuance entry; product status ACTIVE

## pay
**Validation:**
- Balance enforced per payment (`check_balance_on_payment=True`)
- Amount > 0 and ≤ remaining
- Partial allowed — multiple payments
- Over-payment guard

**Success effects:**
- `PURCHASE_PAYMENT` (`project.fund → vendor.fund`)
- ▼ project → ▲ vendor; `amount_settled` ↑

## move items
**Validation:**
- `can_create_movement=True`; operation not reversed
- Qty ≤ item remaining qty
- Product allowed (active/obligated); officer staff + active

**Success effects:**
- `PURCHASE_MOVEMENT` ledger entry
- Lazy product creation; product status ACTIVE; remaining qty ↓

## adjust items
**Validation:**
- `is_items_adjustable=True`; not reversed / not a reversal
- ≥ 1 item changed; new qty/price parse
- New qty ≥ already moved

**Success effects:**
- `InvoiceItemAdjustment` + lines; item adjusted qty/price
- Accounting `Adjustment` + `*_ADJUSTMENT` transaction
- Inventory ledger `*_ADJUSTMENT` entries

## adjust
**Validation:**
- `can_adjust=True`; not reversed / not a reversal
- Adjustment type allowed for PURCHASE
- Amount > 0; officer staff + active

**Success effects:**
- `PURCHASE_ADJUSTMENT_INCREASE` / `PURCHASE_ADJUSTMENT_DECREASE` (non-cash)
- `effective_amount` delta

## reverse
**Validation:**
- Not already reversed / not a reversal / reason required
- Blocked if any payment (`PURCHASE_PAYMENT`) exists
- Blocked if any non-reversed movement lines exist
- Blocked if any non-reversed adjustment exists

**Success effects:**
- Reversal record; counter-transaction for issuance only
- Negated product ledger entry

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

Tasks:
- [x] Verify save creates only one PURCHASE_ISSUANCE transaction (not payment — not one-shot)
- [x] Verify no PURCHASE_PAYMENT transaction is created on save
- [x] Verify PURCHASE_ISSUANCE direction: source=project.fund, target=vendor.fund
- [x] Verify PURCHASE_ISSUANCE is non-cash: project fund balance unchanged after save
- [x] Verify amount_remaining_to_settle equals full amount after creation
- [x] Verify is_not_fully_settled after creation
- [x] Verify source must be a Project entity (non-project source raises ValidationError)
- [x] Verify source must be active (inactive source raises ValidationError)
- [x] Verify source fund must be active
- [x] Verify destination must be a Vendor entity (non-vendor destination raises ValidationError)
- [x] Verify project entity as destination raises ValidationError
- [x] Verify destination must be an active vendor stakeholder (non-stakeholder raises ValidationError)
- [x] Verify destination with inactive stakeholder raises ValidationError
- [x] Verify amount/officer validations (zero, negative, non-staff, inactive)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify payment creates PURCHASE_PAYMENT transaction (direction: project.fund → vendor.fund)
- [x] Verify payment amount_remaining_to_settle decreases correctly
- [x] Verify multiple partial payments are allowed and accumulate
- [x] Verify full payment marks operation as fully settled
- [x] Verify project fund decreases by payment amount (PURCHASE_PAYMENT is cash)
- [x] Verify vendor fund increases by payment amount
- [x] Verify payment cannot exceed remaining amount (over-payment raises ValidationError)
- [x] Verify partial then over-payment raises ValidationError
- [x] Verify zero/negative payment raises ValidationError
- [x] Verify balance enforced on payment (insufficient project fund raises ValidationError)
- [x] Reversal creates reversal operation with correct linkage
- [x] Verify reversal marks original as reversed
- [x] Verify reversal is marked as is_reversal
- [x] Verify reversal inherits amount, source, destination from original
- [x] Verify reversal creates counter-transaction for issuance only
- [x] Verify reversal counter-transaction flips source/target funds
- [x] Verify project fund unchanged after reversal (issuance is non-cash)
- [x] Verify reversal is blocked when any PURCHASE_PAYMENT transaction exists
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [ ] Add FK from Operation to FinancialCategory to enforce category_required at model save level
- [ ] UI: create form — source=Project (url entity), destination=Vendor (from stakeholders), optional invoice formset
- [ ] UI: detail shows total amount, paid so far, remaining; "Record Payment" button
