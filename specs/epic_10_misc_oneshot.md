# EPIC 10 — Miscellaneous One-Shot Operations
> Internal transfers and system-level capital adjustments.

---

### Feature 10.1 — Internal Transfer
**Type:** One-shot (both entities must be internal)
**Transaction flow:**
- Issuance: `source.fund → destination.fund` — type: `INTERNAL_TRANSFER_ISSUANCE`
- Payment: `source.fund → destination.fund` — type: `INTERNAL_TRANSFER_PAYMENT`

Tasks:
- [ ] Verify issuance transaction created with correct direction
- [ ] Verify both source and destination are flagged as internal (`is_internal=True`)
- [ ] Verify reversal: `destination.fund → source.fund`
- [ ] UI: create form — entity dropdowns filtered to internal entities only
- [ ] UI: operation detail shows issuance transaction and reversal button

---

### Feature 10.2 — Capital Gain
**Type:** One-shot
**Transaction flow:**
- Issuance: `system.fund → entity.fund` — type: `CAPITAL_GAIN_ISSUANCE`
- Payment: `system.fund → entity.fund` — type: `CAPITAL_GAIN_PAYMENT`

Tasks:
- [ ] Verify issuance transaction created with correct direction (system → entity)
- [ ] Verify source is the System entity (`is_system=True`)
- [ ] Verify reversal: `entity.fund → system.fund`
- [ ] UI: create form — source locked to System entity
- [ ] UI: operation detail shows issuance transaction and reversal button

---

### Feature 10.3 — Capital Loss
**Type:** One-shot
**Transaction flow:**
- Issuance: `entity.fund → system.fund` — type: `CAPITAL_LOSS_ISSUANCE`
- Payment: `entity.fund → system.fund` — type: `CAPITAL_LOSS_PAYMENT`

Tasks:
- [ ] Verify issuance transaction created with correct direction (entity → system)
- [ ] Verify destination is the System entity (`is_system=True`)
- [ ] Verify reversal: `system.fund → entity.fund`
- [ ] UI: create form — destination locked to System entity
- [ ] UI: operation detail shows issuance transaction and reversal button
