# EPIC 12 — Repayable Operations
> Operations where money is advanced and later recovered through repayments.

---

### Feature 12.1 — Loan
**Type:** Has repayment (`has_repayment=True`, `max_payment_count=-1`)
**Transaction flow:**
- Issuance: `creditor.fund → debtor.fund` — type: `LOAN_ISSUANCE`
- Payment (disbursement): `creditor.fund → debtor.fund` — type: `LOAN_PAYMENT`
- Repayment (recovery): `debtor.fund → creditor.fund` — type: `LOAN_REPAYMENT`

Tasks:
- [ ] Verify issuance transaction created correctly (creditor → debtor)
- [ ] Verify repayment view creates transaction in correct direction: `destination.fund → source.fund`
- [ ] Verify `amount_remaining_to_repay` property works: `issuance_amount - sum(repayments)`
- [ ] Reversal: only issuance is implicitly reversed; repayments must be cleared manually first
- [ ] UI: create form works; detail shows outstanding balance and "Record Repayment" button
- [ ] UI: repayment button shows remaining balance, blocks over-repayment

---

### Feature 12.2 — Worker Advance
**Type:** One-shot issuance + has repayment
**Transaction flow:**
- Issuance: `project.fund → worker.fund` — type: `WORKER_ADVANCE_ISSUANCE`
- Payment: `project.fund → worker.fund` — type: `WORKER_ADVANCE_PAYMENT`
- Repayment (recovery): `worker.fund → project.fund` — type: `WORKER_ADVANCE_REPAYMENT`

Tasks:
- [ ] Verify issuance transaction created correctly (project → worker)
- [ ] Verify repayment view creates transaction: `destination.fund → source.fund` (worker → project)
- [ ] Verify `amount_remaining_to_repay` property works: `issuance_amount - sum(repayments)`
- [ ] Verify destination is an active Stakeholder in the source project
- [ ] UI: create form — source=Project, destination filtered to active workers of that project
- [ ] UI: detail shows advance amount, repaid so far, outstanding; "Record Repayment" button
- [ ] UI: repayment button blocks over-repayment (cannot repay more than advanced)
