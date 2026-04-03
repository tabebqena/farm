# EPIC 9 — Project Capital Operations
> Money flowing into and out of projects between shareholders and funders.

---

### Feature 9.1 — Project Funding
**Type:** One-shot
**Transaction flow:**
- Issuance: `person.fund → project.fund` — type: `PROJECT_FUNDING_ISSUANCE`
- Payment: `person.fund → project.fund` — type: `PROJECT_FUNDING_PAYMENT`

Tasks:
- [ ] Verify issuance transaction created with correct direction (funder → project)
- [ ] Verify reversal: `project.fund → person.fund`
- [ ] UI: create form — destination must be a Project entity
- [ ] UI: operation detail shows issuance transaction, funder and project labels, reversal button

---

### Feature 9.2 — Project Refund
**Type:** One-shot
**Transaction flow:**
- Issuance: `project.fund → person.fund` — type: `PROJECT_REFUND_ISSUANCE`
- Payment: `project.fund → person.fund` — type: `PROJECT_REFUND_PAYMENT`

Tasks:
- [ ] Verify issuance transaction created with correct direction (project → funder)
- [ ] Verify reversal: `person.fund → project.fund`
- [ ] UI: create form — source must be a Project entity
- [ ] UI: operation detail shows issuance transaction and reversal button

---

### Feature 9.3 — Profit Distribution
**Type:** One-shot
**Transaction flow:**
- Issuance: `project.fund → shareholder.fund` — type: `PROFIT_DISTRIBUTION_ISSUANCE`
- Payment: `project.fund → shareholder.fund` — type: `PROFIT_DISTRIBUTION_PAYMENT`

Tasks:
- [ ] Verify issuance transaction created with correct direction (project → shareholder)
- [ ] Verify reversal: `shareholder.fund → project.fund`
- [ ] UI: create form — source must be Project, destination must be Shareholder
- [ ] UI: operation detail shows issuance transaction and reversal button

---

### Feature 9.4 — Loss Coverage
**Type:** One-shot
**Transaction flow:**
- Issuance: `shareholder.fund → project.fund` — type: `LOSS_COVERAGE_ISSUANCE`
- Payment: `shareholder.fund → project.fund` — type: `LOSS_COVERAGE_PAYMENT`

Tasks:
- [ ] Verify issuance transaction created with correct direction (shareholder → project)
- [ ] Verify reversal: `project.fund → shareholder.fund`
- [ ] UI: create form — source is Shareholder, destination is Project
- [ ] UI: operation detail shows issuance transaction and reversal button
