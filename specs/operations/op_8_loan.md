# Loan
**Epic:** 12.1 — Repayable Operations
**Type:** Has repayment (`has_repayment=True`, `max_payment_count=-1`)
**Transaction flow:**
- Issuance: `creditor.fund → debtor.fund` — type: `LOAN_ISSUANCE`
- Payment (disbursement): `creditor.fund → debtor.fund` — type: `LOAN_PAYMENT`
- Repayment (recovery): `debtor.fund → creditor.fund` — type: `LOAN_REPAYMENT`

**Actions:** create, pay, repay, reverse.

## create
**Validation:**
- Source (creditor) can be a Person or Project entity — enforced via `clean_source()`
- Destination (debtor) can be a Person or Project entity; must differ from source — enforced via `clean_destination()` + `clean()` (`source_id != destination_id`)
- Both entities must be `active=True`
- Source entity's fund must be `active=True`
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`
- Balance @ create: **exempt** (issuance unguarded); multi-stage (not one-shot)

**Success effects:**
- `LOAN_ISSUANCE` created on save (non-cash memo)
- No payment on save — disbursements happen later via **pay**

## pay (disbursement)
**Validation:**
- Balance enforced per disbursement (`check_balance_on_payment=True`)
- Amount > 0 and ≤ remaining
- Partial allowed — multiple disbursements (`max_payment_transaction_count=-1`)
- Over-payment guard

**Success effects:**
- `LOAN_PAYMENT` (`creditor.fund → debtor.fund`)
- ▼ creditor → ▲ debtor; `amount_settled` ↑

## repay
**Validation:**
- Amount > 0 and ≤ remaining
- Over-repayment guard
- Remaining is capped by the disbursed amount: active repayments can never
  exceed the total `LOAN_PAYMENT` sum. A loan with **no** disbursement is not
  repayable (`amount_remaining_to_repay` = 0).

**Success effects:**
- `LOAN_REPAYMENT` (`debtor.fund → creditor.fund`)
- ▼ debtor → ▲ creditor; `amount_repayed` ↑

## reverse
**Validation:**
- Not already reversed / not a reversal / reason required
- Blocked if any disbursement (`LOAN_PAYMENT`) exists
- *Pending:* blocked if outstanding repayments exist (see Gap notes)

**Success effects:**
- Reversal record; counter-transaction for issuance only

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

Tasks:
- [x] Verify issuance transaction created correctly (creditor → debtor, type `LOAN_ISSUANCE`)
- [x] Verify both entities must be `active=True`
- [x] Verify source fund must be `active=True`
- [x] Verify amount/officer validations (zero, negative, non-staff, inactive, no-user)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify repayment view creates transaction in correct direction: `destination.fund → source.fund` (debtor → creditor)
- [x] Verify repayment transaction type is `LOAN_REPAYMENT`
- [x] Verify `amount_remaining_to_repay` property: capped by the disbursed amount
  (`min(issuance_amount, sum(LOAN_PAYMENT)) - sum(repayments)`)
- [x] Verify repayment cannot exceed remaining balance (`amount_remaining_to_repay`)
- [x] Verify repayment is blocked when no disbursement (`LOAN_PAYMENT`) exists
- [x] Verify repayment cannot exceed the total disbursed amount (payment sum)
- [x] Verify creditor fund decreases after payment disbursement
- [x] Verify debtor fund increases after payment disbursement
- [x] Verify multiple payment disbursements allowed
- [x] Verify debtor fund decreases after repayment
- [x] Verify creditor fund increases after repayment
- [x] Verify multiple repayments accumulate correctly
- [x] Verify full repayment marks as fully repayed
- [x] Reversal: only issuance counter-transaction is created (payment disbursements block reversal)
- [x] Verify reversal blocked when payment disbursements exist
- [ ] Verify reversal blocked if outstanding repayments exist (debtor → creditor LOAN_REPAYMENT transactions)
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [ ] UI: create form works; detail shows outstanding balance and "Record Repayment" button
- [ ] UI: repayment button shows remaining balance, blocks over-repayment
