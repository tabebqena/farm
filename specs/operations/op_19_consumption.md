# Consumption
**Epic:** Inventory / Livestock — One-Shot
**Type:** One-shot, auto-settled, removes assets (`has_invoice=True`)

**Transaction flow:**
- Issuance: `project → system.fund` — type: `CONSUMPTION_ISSUANCE`
- Payment: `project → system.fund` — type: `CONSUMPTION_PAYMENT`

**Actions:** create, reverse.

## create
**Validation:**
- Source must be a Project entity
- Destination must be the System entity (`is_system=True`)
- Both entities `active=True`; source fund `active=True`
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`
- Balance @ create: **exempt** (no-balance write-off) — `E@create` pay (one-shot)

**Success effects:**
- `CONSUMPTION_ISSUANCE` + `CONSUMPTION_PAYMENT` created on save
- Immediately settled (`is_fully_settled=True`)
- Fund deltas: ▼ project → ▲ system (virtual)
- ✓ product ledger issuance **and** auto-created movement lines (`_auto_create_inventory_movements()` now includes CONSUMPTION, mirroring DEATH)
- ✓ `CONSUMPTION_MOVEMENT` ledger entry written per movement line
- ✓ Product status → `CONSUMED` (blocked from new operations unless reversed/adjusted)

## reverse
**Validation:**
- Not already reversed / not a reversal / reason required

**Success effects:**
- Reversal record; counter-transactions for issuance + payment
- Negated product ledger entries
- ✓ Auto-created movement lines reversed (reversal lines linked via `reversal_of`)
- Product status remains `CONSUMED` (consistent with DEATH/DEAD reversal behaviour)

**Tests:** [`test_consumption_consumption_create.py`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py), [`test_consumption_consumption_reversal.py`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_reversal.py), [`test_consumption_stock_detail.py`](../../apps/app_operation/tests/operations/inventory/test_consumption_stock_detail.py).
