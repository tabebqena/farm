# EPIC 9 — Project Capital Operations
> Money flowing into and out of projects between shareholders and funders.

---

### Feature 9.1 — Project Funding
**Type:** One-shot, auto-settled
**Transaction flow:**
- Issuance: `person.fund → project.fund` — type: `PROJECT_FUNDING_ISSUANCE`
- Payment: `person.fund → project.fund` — type: `PROJECT_FUNDING_PAYMENT`

**Settlement:** Fully settled immediately — `is_fully_settled=True`, `amount_settled == amount`, `amount_remaining_to_settle == 0`

**Validation:**
- Source must be a Person entity
- Source must be a registered active shareholder of the destination project
- Destination must be a Project entity
- Both entities must be `active=True`
- Source entity's fund must be `active=True`
- Source fund must have sufficient balance (`fund.balance >= amount`)
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

Tasks:
- [x] Verify both `PROJECT_FUNDING_ISSUANCE` and `PROJECT_FUNDING_PAYMENT` transactions are created on save
- [x] Verify transaction fund direction: `person.fund → project.fund` for both
- [x] Verify operation is fully settled immediately
- [x] Verify all validation rules listed above (including insufficient funds check)
- [x] Verify source must be a registered shareholder of the destination project
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `create_payment_transaction()` is blocked after creation
- [x] Verify reversal creates counter-transactions: `project.fund → person.fund`
- [x] Verify funder balance decreases after funding
- [x] Verify funder balance restored after reversal
- [ ] UI: create form — source filtered to Person entities, destination filtered to Project entities
- [ ] UI: operation detail shows both transactions and reversal button

---

### Feature 9.2 — Project Refund
**Type:** One-shot, auto-settled
**Transaction flow:**
- Issuance: `project.fund → person.fund` — type: `PROJECT_REFUND_ISSUANCE`
- Payment: `project.fund → person.fund` — type: `PROJECT_REFUND_PAYMENT`

**Settlement:** Fully settled immediately — `is_fully_settled=True`, `amount_settled == amount`, `amount_remaining_to_settle == 0`

**Validation:**
- Source must be a Project entity
- Destination must be a Person entity
- Destination must be a registered active shareholder of the source project
- Both entities must be `active=True`
- Source entity's fund must be `active=True`
- Source fund must have sufficient balance (`fund.balance >= amount`)
- Refund amount must not exceed the net amount funded by the shareholder into this project
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

Tasks:
- [x] Verify both `PROJECT_REFUND_ISSUANCE` and `PROJECT_REFUND_PAYMENT` transactions are created on save
- [x] Verify transaction fund direction: `project.fund → person.fund` for both
- [x] Verify operation is fully settled immediately
- [x] Verify all validation rules listed above (including insufficient funds check)
- [x] Verify destination must be a registered shareholder of the source project
- [x] Verify refund amount cannot exceed shareholder's net funded amount (cumulative cap across multiple refunds)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `create_payment_transaction()` is blocked after creation
- [x] Verify reversal creates counter-transactions: `person.fund → project.fund`
- [x] Verify project balance decreases after refund
- [x] Verify project balance restored after reversal
- [x] Verify shareholder balance increases after refund
- [x] Verify shareholder balance restored after reversal
- [ ] UI: create form — source filtered to Project entities, destination filtered to Person entities
- [ ] UI: operation detail shows both transactions and reversal button

---

### Feature 9.3 — Profit Distribution
**Type:** One-shot, auto-settled
**Transaction flow:**
- Issuance: `project.fund → shareholder.fund` — type: `PROFIT_DISTRIBUTION_ISSUANCE`
- Payment: `project.fund → shareholder.fund` — type: `PROFIT_DISTRIBUTION_PAYMENT`

**Settlement:** Fully settled immediately — `is_fully_settled=True`, `amount_settled == amount`, `amount_remaining_to_settle == 0`

**Validation:**
- Source must be a Project entity
- Destination must be a Person (shareholder) entity
- Both entities must be `active=True`
- Source entity's fund must be `active=True`
- Source fund must have sufficient balance (`fund.balance >= amount`)
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

Tasks:
- [ ] Verify both `PROFIT_DISTRIBUTION_ISSUANCE` and `PROFIT_DISTRIBUTION_PAYMENT` transactions are created on save
- [ ] Verify transaction fund direction: `project.fund → shareholder.fund` for both
- [ ] Verify operation is fully settled immediately
- [ ] Verify all validation rules listed above (including insufficient funds check)
- [ ] Verify immutability of `source`, `destination`, `amount` after save
- [ ] Verify `create_payment_transaction()` is blocked after creation
- [ ] Verify reversal creates counter-transactions: `shareholder.fund → project.fund`
- [ ] Verify project balance decreases after distribution
- [ ] Verify project balance restored after reversal
- [ ] UI: create form — source filtered to Project entities, destination filtered to Person entities
- [ ] UI: operation detail shows both transactions and reversal button

---

### Feature 9.4 — Loss Coverage
**Type:** One-shot, auto-settled
**Transaction flow:**
- Issuance: `shareholder.fund → project.fund` — type: `LOSS_COVERAGE_ISSUANCE`
- Payment: `shareholder.fund → project.fund` — type: `LOSS_COVERAGE_PAYMENT`

**Settlement:** Fully settled immediately — `is_fully_settled=True`, `amount_settled == amount`, `amount_remaining_to_settle == 0`

**Validation:**
- Source must be a Person (shareholder) entity
- Destination must be a Project entity
- Both entities must be `active=True`
- Source entity's fund must be `active=True`
- Source fund must have sufficient balance (`fund.balance >= amount`)
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`

**Immutability:** `source`, `destination`, `amount` cannot be changed after save

Tasks:
- [ ] Verify both `LOSS_COVERAGE_ISSUANCE` and `LOSS_COVERAGE_PAYMENT` transactions are created on save
- [ ] Verify transaction fund direction: `shareholder.fund → project.fund` for both
- [ ] Verify operation is fully settled immediately
- [ ] Verify all validation rules listed above (including insufficient funds check)
- [ ] Verify immutability of `source`, `destination`, `amount` after save
- [ ] Verify `create_payment_transaction()` is blocked after creation
- [ ] Verify reversal creates counter-transactions: `project.fund → shareholder.fund`
- [ ] Verify shareholder balance decreases after loss coverage
- [ ] Verify shareholder balance restored after reversal
- [ ] UI: create form — source filtered to Person entities, destination filtered to Project entities
- [ ] UI: operation detail shows both transactions and reversal button
