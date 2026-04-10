# Loan
**Epic:** 12.1 — Repayable Operations
**Type:** Has repayment (`has_repayment=True`, `max_payment_count=-1`)
**Transaction flow:**
- Issuance: `creditor.fund → debtor.fund` — type: `LOAN_ISSUANCE`
- Payment (disbursement): `creditor.fund → debtor.fund` — type: `LOAN_PAYMENT`
- Repayment (recovery): `debtor.fund → creditor.fund` — type: `LOAN_REPAYMENT`

**Validation:**
- Source (creditor) can be a Person or Project entity
- Destination (debtor) can be a Person or Project entity; must differ from source
- Both entities must be `active=True`
- Source entity's fund must be `active=True`
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

Tasks:
- [ ] Verify issuance transaction created correctly (creditor → debtor, type `LOAN_ISSUANCE`)
- [ ] Verify both entities must be `active=True`
- [ ] Verify source fund must be `active=True`
- [ ] Verify amount/officer validations (zero, negative, non-staff, inactive, no-user)
- [ ] Verify immutability of `source`, `destination`, `amount` after save
- [ ] Verify repayment view creates transaction in correct direction: `destination.fund → source.fund` (debtor → creditor)
- [ ] Verify repayment transaction type is `LOAN_REPAYMENT`
- [ ] Verify `amount_remaining_to_repay` property: `issuance_amount - sum(repayments)`
- [ ] Verify repayment cannot exceed remaining balance (`amount_remaining_to_repay`)
- [ ] Verify creditor fund decreases after issuance
- [ ] Verify debtor fund increases after issuance
- [ ] Verify debtor fund decreases after repayment
- [ ] Verify creditor fund increases after repayment
- [ ] Reversal: only issuance is implicitly reversed; repayments must be cleared manually first
- [ ] Verify reversal blocked if outstanding repayments exist
- [ ] Verify reversal marks original as reversed and sets `reversed_by`
- [ ] Verify cannot reverse an already-reversed operation
- [ ] UI: create form works; detail shows outstanding balance and "Record Repayment" button
- [ ] UI: repayment button shows remaining balance, blocks over-repayment
