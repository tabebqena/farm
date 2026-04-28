# Adjustment
**App:** `app_adjustment`
**Concept:** Post-hoc corrections to the amount of a Purchase, Sale, or Expense operation. An adjustment creates a single transaction that either increases or decreases the effective obligation of the linked operation without changing the original operation's `amount` field.

---

## AdjustmentType

Adjustments are typed and the type implicitly determines the effect (INCREASE or DECREASE):

**Purchase adjustments (decreasing what we owe vendor):**
- `PURCHASE_RETURN`, `PURCHASE_DISCOUNT`, `PURCHASE_OVERCHARGE`, `PURCHASE_SHORTAGE`, `PURCHASE_DAMAGE`, `PURCHASE_GENERAL_REDUCTION`

**Purchase adjustments (increasing what we owe vendor):**
- `PURCHASE_UNDERCHARGE`, `PURCHASE_TAX_ADDITION`, `PURCHASE_FREIGHT`, `PURCHASE_GENERAL_INCREASE`

**Sale adjustments (decreasing what client owes us):**
- `SALE_RETURN`, `SALE_DISCOUNT`, `SALE_OVERCHARGE`, `SALE_SHORTAGE`, `SALE_DAMAGE`, `SALE_WRITE_OFF`, `SALE_GENERAL_REDUCTION`

**Sale adjustments (increasing what client owes us):**
- `SALE_UNDERCHARGE`, `SALE_TAX_ADDITION`, `SALE_LATE_FEE`, `SALE_GENERAL_INCREASE`

**Expense adjustments** (mapped to `EXPENSE_ADJUSTMENT_INCREASE` / `EXPENSE_ADJUSTMENT_DECREASE` transactions)

---

## Transaction flow

- The adjustment reuses the linked operation's `payment_source_fund` and `payment_target_fund`.
- A DECREASE adjustment creates a transaction in the same direction as the original, but with type `*_ADJUSTMENT_DECREASE` — effectively recording a credit against the obligation.
- An INCREASE adjustment creates a transaction with type `*_ADJUSTMENT_INCREASE`.
- The `effect` field (`INCREASE`/`DECREASE`) is auto-set from the type during `clean()`.

---

## Validation
- `operation` must be a Purchase, Sale, or Expense operation (other types raise ValidationError)
- `type` must match the operation's operation_type (Purchase types on Purchase ops, etc.)
- General adjustment types (`*_GENERAL_INCREASE` / `*_GENERAL_REDUCTION`) require a non-empty `reason`
- `amount` must be positive
- `officer` must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`

**Immutability:** `operation`, `type`, `amount`, `effect` cannot be changed after save

---

## Effective amount

`operation.effective_amount` (or equivalent) = `operation.amount` +/- sum of all active (non-reversed) adjustments.

---

## Tasks

**Transactions**
- [x] Verify PURCHASE adjustment creates PURCHASE_ADJUSTMENT_INCREASE or PURCHASE_ADJUSTMENT_DECREASE transaction
- [x] Verify SALE adjustment creates SALE_ADJUSTMENT_INCREASE or SALE_ADJUSTMENT_DECREASE transaction
- [x] Verify EXPENSE adjustment creates EXPENSE_ADJUSTMENT_INCREASE or EXPENSE_ADJUSTMENT_DECREASE transaction
- [x] Verify adjustment transaction source and target match the operation's payment funds
- [x] Verify adjustment transaction amount matches the adjustment amount

**Type → Effect mapping**
- [x] Verify PURCHASE_RETURN sets DECREASE effect
- [x] Verify PURCHASE_DISCOUNT sets DECREASE effect
- [x] Verify PURCHASE_UNDERCHARGE sets INCREASE effect
- [x] Verify PURCHASE_FREIGHT sets INCREASE effect
- [x] Verify SALE_RETURN sets DECREASE effect
- [x] Verify SALE_WRITE_OFF sets DECREASE effect
- [x] Verify SALE_LATE_FEE sets INCREASE effect
- [x] Verify GENERAL_REDUCTION types set DECREASE effect
- [x] Verify GENERAL_INCREASE types set INCREASE effect

**Validation**
- [x] Verify non-adjustable operation type (e.g. LOAN) raises ValidationError
- [x] Verify Purchase and Sale operations are adjustable
- [x] Verify GENERAL type without reason raises ValidationError
- [x] Verify GENERAL type with reason saves OK
- [x] Verify non-general type without reason saves OK
- [x] Verify amount zero raises ValidationError
- [x] Verify amount negative raises ValidationError
- [x] Verify officer user must be staff
- [x] Verify officer must be active

**Immutability**
- [x] Verify `operation` is immutable after save
- [x] Verify `type` is immutable after save
- [x] Verify `amount` is immutable after save
- [x] Verify `effect` cannot be changed independently of type

**Effective amount**
- [x] No adjustments returns base operation amount
- [x] Single DECREASE adjustment reduces effective amount
- [x] Single INCREASE adjustment raises effective amount
- [x] Mixed adjustments combine correctly
- [x] Multiple DECREASE adjustments accumulate
- [x] Reversed adjustment excluded from effective amount

**Reversal**
- [x] `reverse()` returns a new Adjustment instance
- [x] Reversal is linked to the original (`reversal_of`)
- [x] Original is marked as reversed
- [x] Reversal is marked as `is_reversal`
- [x] Reversal inherits type, amount, operation from original
- [x] Reversal creates a counter-transaction
- [x] Counter-transaction flips source and target funds
- [x] Cannot reverse an already-reversed adjustment
- [x] Cannot reverse a reversal

**UI**
- [ ] UI: add adjustment form on Purchase/Sale/Expense operation detail
- [ ] UI: list adjustments with type, amount, effect, and reversal button on operation detail
- [ ] UI: show effective amount on operation detail (base ± adjustments)
