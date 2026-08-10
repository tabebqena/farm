# Birth
**Epic:** Inventory / Livestock — One-Shot
**Type:** One-shot, auto-settled, creates assets (`creates_assets=True`, `has_invoice=True`)

**Transaction flow:**
- Issuance: `system.fund → project` — type: `BIRTH_ISSUANCE`
- Payment: `system.fund → project` — type: `BIRTH_PAYMENT`

**Actions:** create, move items (auto), reverse.

## create
**Validation:**
- Source must be the System entity (`is_system=True`) — enforced via `clean_source()`
- Destination must be a Project entity (`is_project=True`) — enforced via `clean_destination()`
- Both entities `active=True`; source fund `active=True`
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`
- Balance @ create: **exempt** (system payer) — `E@create` pay (one-shot)

**Success effects:**
- `BIRTH_ISSUANCE` + `BIRTH_PAYMENT` created on save
- Immediately settled (`is_fully_settled=True`)
- Fund deltas: ▼ system (virtual) → ▲ project assets
- ✓ product ledger issuance + auto movement lines (inbound); new asset status ACTIVE

**Inventory validation (enforced):**
- Unit consistency: quantity must be a multiple of `product_template.minimum_quantity`
- Identity: for `INDIVIDUAL` tracking, a tag/`unique_id` is required and must be unique per entity (DB `UniqueConstraint` + form rule)

## move items (auto)
**Success effects:**
- `BIRTH_MOVEMENT` ledger entry (auto inbound, valued at the new asset's cost)
- Lazy product creation; product status ACTIVE (new asset)

## reverse
**Validation:**
- Not already reversed / not a reversal / reason required

**Success effects:**
- Reversal record; counter-transactions for issuance + payment
- Negated product ledger entry; auto movement lines reversed

**Gaps:** None — dedicated test suite under `apps/app_operation/tests/operations/birth/` (`test_birth_birth_create.py`, `test_birth_birth_reversal.py`) covers create (validation, issuance + payment, auto inbound movement, lazy product creation, ACTIVE status, ledger) and reverse (reversal record, counter-tx, auto lines reversed, negated ledger). Destination-project entity check is enforced via `clean_destination()` (tests: `test_destination_must_be_project_entity`, `test_destination_world_entity_raises_validation_error`). See [Gap notes](operations-comparison.md#gap--discrepancy-notes).
