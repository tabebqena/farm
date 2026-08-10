# Death
**Epic:** Inventory / Livestock — One-Shot
**Type:** One-shot, auto-settled, removes assets (`has_invoice=True`)

**Transaction flow:**
- Issuance: `project → system.fund` — type: `DEATH_ISSUANCE`
- Payment: `project → system.fund` — type: `DEATH_PAYMENT`

**Actions:** create, move items (auto), reverse.

## create
**Validation:**
- Source must be a Project entity (`clean_source` on `DeathOperation`)
- Destination must be the System entity (`is_system=True`)
- Both entities `active=True`; source fund `active=True`
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`
- Balance @ create: **exempt** (no-balance write-off) — `E@create` pay (one-shot)

**Success effects:**
- `DEATH_ISSUANCE` + `DEATH_PAYMENT` created on save
- Immediately settled (`is_fully_settled=True`)
- Fund deltas: ▼ project assets → ▲ system (virtual)
- ✓ product ledger issuance + auto movement lines (outbound); product status DEAD

## move items (auto)
**Success effects:**
- `DEATH_MOVEMENT` ledger entry (auto outbound)
- Product status DEAD

## reverse
**Validation:**
- Not already reversed / not a reversal / reason required

**Success effects:**
- Reversal record; counter-transactions for issuance + payment
- Negated product ledger entry; auto movement lines reversed

**Status:**
- `clean_source` implemented on `DeathOperation` — source must be a Project entity (enforced via `BaseModel.clean_fields()` → `clean_source`).
- Dedicated tests: [`test_death_death_create.py`](../../apps/app_operation/tests/operations/inventory/test_death_death_create.py) under `apps/app_operation/tests/operations/inventory/`.
