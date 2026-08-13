# Death
**Epic:** Inventory / Livestock — One-Shot
**Type:** One-shot, auto-settled, removes assets (`has_invoice=True`)

**Transaction flow:**
- Issuance: `project → system.fund` — type: `DEATH_ISSUANCE`
- Payment: `project → system.fund` — type: `DEATH_PAYMENT` — **non-cash bookkeeping** (excluded from `payment_types()`; the payment never affects the project's fund balance)

**Actions:** create, move items (auto), reverse.

## create
**Validation:**
- Source must be a Project entity (`clean_source` on `DeathOperation`)
- Destination must be the System entity (`is_system=True`)
- Both entities `active=True`; source fund `active=True`
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`
- Balance @ create: **exempt** (no-balance write-off) — `E@create` pay (one-shot)
- Should linked to product
- The affected product should be can_die
**Success effects:**
- `DEATH_ISSUANCE` + `DEATH_PAYMENT` created on save
- Immediately settled (`is_fully_settled=True`)
- Fund deltas: **no cash flow** — ▼ project assets (inventory value only) → ▲ system (virtual, non-cash)
- ✓ product ledger issuance + auto movement lines (outbound); product status DEAD
- The inventory value decreased by the DEAD product value.

**Valuation / end_assets (no double count):**
- A death reduces `end_assets` **exactly once**, via movement-based inventory value (the dead animal's carried cost).
- `DEATH_PAYMENT` is non-cash — it never drains the project's fund balance.

**Inventory validation (enforced):**
- Availability: quantity must not exceed the product's physically-present on-hand (ledger)
- Ownership: the selected product must belong to the source project
- Unit consistency: quantity must be a multiple of `product_template.minimum_quantity`

## move items (auto)
**Success effects:**
- `DEATH_MOVEMENT` ledger entry (auto outbound, valued at the product's carried cost)
- Product status DEAD

## reverse
**Validation:**
- Not already reversed / not a reversal / reason required
- Reversal dependency guard: blocked if the product was moved again in a later non-reversed outbound operation

**Success effects:**
- Reversal record; counter-transactions for issuance + payment
- Negated product ledger entry; auto movement lines reversed
- ✓ Product status **restored to ACTIVE** (reversal-aware `Product.status`)

**Status:**
- `clean_source` implemented on `DeathOperation` — source must be a Project entity (enforced via `BaseModel.clean_fields()` → `clean_source`).
- Dedicated tests: [`test_death_death_create.py`](../../apps/app_operation/tests/operations/inventory/test_death_death_create.py) under `apps/app_operation/tests/operations/inventory/`.
