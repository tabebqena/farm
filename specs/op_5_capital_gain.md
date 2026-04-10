# Capital Gain
**Epic:** 10.2 — Miscellaneous One-Shot Operations
**Type:** One-shot
**Transaction flow:**
- Issuance: `system.fund → entity.fund` — type: `CAPITAL_GAIN_ISSUANCE`
- Payment: `system.fund → entity.fund` — type: `CAPITAL_GAIN_PAYMENT`

Tasks:
- [x] Verify issuance and payment transactions are created
- [x] Verify transaction types are `CAPITAL_GAIN_ISSUANCE` and `CAPITAL_GAIN_PAYMENT`
- [x] Verify transaction funds: source=system.fund, target=project.fund
- [x] Verify source is the System entity (`is_system=True`)
- [x] Verify non-system source (person or world entity) raises ValidationError
- [x] Verify destination is a project entity and must be active
- [x] Verify project fund increases by the gain amount
- [x] Verify operation is fully settled immediately after creation
- [x] Verify amount/officer validations (zero, negative, non-staff, inactive, no-user)
- [x] Verify source, destination, and amount are immutable after creation
- [x] Verify one-shot constraint prevents a second payment transaction
- [x] Verify reversal creates a reversal operation linked to the original
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify reversal counter-transactions flip funds (project.fund → system.fund)
- [x] Verify counter-transactions preserve transaction type
- [x] Verify project fund is restored to pre-gain balance after reversal
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [ ] UI: create form — source locked to System entity
- [ ] UI: operation detail shows issuance transaction and reversal button
