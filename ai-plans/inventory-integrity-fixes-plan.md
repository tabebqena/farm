# Plan: Inventory & Farm-Domain Integrity Fixes

**Source of truth:** verified review of the AI revision of `specs/operations/operations-comparison.md` against the real code in `apps/app_inventory`, `apps/app_operation`, `apps/app_adjustment`, `apps/app_transaction`, `apps/app_base`.

**Guiding principle:** the ledger is append-only + idempotent (DB-unique `idempotency_key`) and that is a strength — keep it. Every fix below adds *guards* and *explicit effects* on top of that ledger, never rewrite-able state.

**Verdicts that shape this plan (verified):**
- Already implemented but under-documented (docs-only): status guards (`Product.validate_active`), `quantity > 0` validators, product–operation compatibility (`accepts_operation`), item-total reconciliation (`_validate_item_totals`).
- Genuine gaps (code fixes): availability, ownership/location, unit consistency, downstream date/period + closed-period, concurrency, lifecycle/reversal semantics, birth tag uniqueness.
- Confirmed intentional (document only): internal-client Sale clones product rows (SOLD on source, ACTIVE on client) — not a bug.

**Confirmed decisions (user, 2026-08-10):**
1. **Reversal + status:** reversing Death/Sale/Consumption restores the product to ACTIVE.
2. **Valuation method:** use the purchase price (cost carried on the batch / `unit_price` per product). Add a code comment that other methods (moving average, FIFO) may be added later.
3. **Internal-client Sale clone:** keep the current clone behavior — no double-entry error, the source copy is marked SOLD and the client copy ACTIVE. Do NOT change `create_from_session()`.
4. **Stock Transfer feature:** OUT OF SCOPE for now — do not add a physical stock-transfer operation.
5. **Reconciliation/stocktake feature:** OUT OF SCOPE for now — do not add a stock-adjustment operation yet.

---

## Fix 1 — Stock ownership / location validation

**Problem:** `InvoiceItemSelectForm.selected_product` uses `Product.objects.all()` (no entity filter), so DEATH/CONSUMPTION/CAPITAL on project A can select project B's asset. The movement view also derives products with no ownership check.

**Files:**
- `apps/app_inventory/forms.py` — `InvoiceItemSelectForm` (queryset filter + `clean`), `InvoiceItemCreateForm`
- `apps/app_inventory/views.py` — `create_inventory_movement`, `register_deferred_movements`
- `apps/app_inventory/models.py` — `InventoryMovementLine.clean`

**Changes:**
1. In `InvoiceItemSelectForm.__init__`, accept the owning `entity` (the operation's source project for SALE/DEATH/CONSUMPTION) and filter `selected_product` to `Product.objects.filter(entity=entity)`.
2. Add a model-level guard in `InventoryMovementLine.clean()`: for outbound operations (SALE, DEATH, CONSUMPTION), reject a movement line whose `product.entity != operation.source`. For PURCHASE/BIRTH, allow (product is created owned by source; BIRTH product is lazy-created).
3. In `create_inventory_movement`, when deriving `first_product`, assert `first_product.entity == operation.source` for outbound ops.

**Tests:** add to `apps/app_inventory/tests/test_inventory_movement.py` + death/consumption create tests: selecting another project's product raises `ValidationError`; form queryset only lists the project's products.

**Verify:** `pytest -q apps/app_inventory apps/app_operation/tests/operations/inventory`

---

## Fix 2 — Inventory availability guard (outbound)

**Problem:** no check that the source project physically holds the stock being moved. `InventoryMovementLine.clean()` only enforces the per-invoice-item over-delivery limit; a DEATH can write off more heads than the batch holds, and a SALE can dispatch feed never received.

**Files:**
- `apps/app_inventory/models.py` — `InventoryMovementLine.clean`, new helper
- `apps/app_operation/models/operation.py` — `_auto_create_inventory_movements` (DEATH/CONSUMPTION), `save_inventory`
- `apps/app_operation/models/proxies/op_sale.py` — `create_from_session`

**Changes:**
1. Add a helper on `Product` or `ProductLedgerEntry` to compute the physically present quantity as of the movement date for a given product (reuse `state_as_of()`; count `MOVEMENT_TYPES` entries).
2. In `InventoryMovementLine.clean()` (non-reversal, outbound ops only), reject `movement_quantity > physically_present_quantity(product, date)`.
3. For DEATH/CONSUMPTION auto lines and SALE wizard delivered qty, validate the batch/commodity quantity before creating the movement line (fail the whole operation atomically).

**Tests:** DEATH of a batch beyond on-hand → `ValidationError`; SALE of more feed than received → `ValidationError`; boundary equal-to-available passes; reversal lines are exempt.

**Verify:** `pytest -q apps/app_inventory apps/app_operation/tests/operations/inventory apps/app_operation/tests/operations/sale`

---

## Fix 3 — Concurrency protection (remaining qty / availability)

**Problem:** remaining-qty and availability checks are read-then-write aggregates with no row locking; two concurrent movements can both pass. DB unique `idempotency_key` stops exact duplicates, not overlapping distinct movements.

**Files:**
- `apps/app_inventory/models.py` — `InventoryMovementLine.clean`, `record_movement_line`
- `apps/app_inventory/views.py` — `create_inventory_movement`, `register_deferred_movements`
- `apps/app_base/mixins.py` — `LinkedPaymentTransactionMixin` balance check

**Changes:**
1. Wrap availability + insert of movement lines in `db_transaction.atomic()` and lock the affected product rows with `select_for_update()`.
2. For the fund balance check in `create_payment_transaction`, `select_for_update` the payer fund row before `can_pay()` (guards concurrent payments).
3. Keep `idempotency_key` as the final DB backstop.

**Tests:** simulate two sequential movements on the same product; assert the second is rejected once stock is insufficient. (True parallel race test can be a documented manual check.)

**Verify:** `pytest -q apps/app_inventory apps/app_transaction`

---

## Fix 4 — Unit / UOM consistency

**Problem:** `ProductTemplate.minimum_quantity` is only used as the HTML `step` attribute; no model-level rule that movement/consumption quantity respects the template's unit (`Head` vs `Kg`) or minimum increment.

**Files:**
- `apps/app_inventory/models.py` — `InventoryMovementLine.clean`, `InvoiceItem.clean`
- `apps/app_inventory/forms.py` — quantity field validation

**Changes:**
1. Add validation that a movement/consumption quantity is a positive multiple of `product_template.minimum_quantity`.
2. Document `default_unit` semantics on the model docstring so Kg/Head mistakes are visible. (No schema change.)

**Tests:** fractional head movement rejected; multiple-of-minimum passes; per-template step respected.

**Verify:** `pytest -q apps/app_inventory`

---

## Fix 5 — Downstream date/period + closed-period guards

**Problem:** `Operation.clean()` blocks *new operations* in a closed period and auto-assigns the period, but payments, repayments, movement lines and adjustments accept arbitrary dates with no closed-period check. Code TODOs: `# TODO add financial period closing` in `apps/app_base/mixins.py`.

**Files:**
- `apps/app_base/mixins.py` — new shared closed-period validation helper
- `apps/app_operation/views/record_transaction.py` — `record_transaction_payment`, `record_transaction_repayment`
- `apps/app_inventory/views.py` — `create_inventory_movement`, `register_deferred_movements`
- `apps/app_operation/views/adjustment.py` — `record_accounting_adjustment`, `record_item_adjustment`

**Changes:**
1. Extract the closed-period predicate already used in `Operation.clean()` into a reusable helper (entity + date → bool).
2. Apply it to the `date` of every payment/repayment/movement/adjustment: reject dates inside a closed period (mirror the existing reversal exemption: reversals may land in an open period).
3. Keep the operation-period auto-assignment unchanged.

**Tests:** payment/movement/adjustment dated into a closed period → rejected; dated into an open period → allowed; reversal into open period → allowed.

**Verify:** `pytest -q apps/app_operation apps/app_inventory apps/app_adjustment`

---

## Fix 6 — Birth / individual-tag identity

**Problem:** tag validation in `InvoiceItemCreateForm.clean()` is commented out, and `Product.unique_id` is `db_index=True` but not unique — duplicate tags are possible.

**Files:**
- `apps/app_inventory/forms.py` — `InvoiceItemCreateForm.clean`
- `apps/app_inventory/models.py` — `Product.unique_id` (unique constraint) + migration
- `apps/app_inventory/migrations/` — new migration

**Changes:**
1. Restore the required-tag rule: for templates with `tracking_mode=INDIVIDUAL` (and/or `has_tag=True`), `unique_id` is required.
2. Add a `UniqueConstraint` (e.g. on `(entity, unique_id)` where `unique_id IS NOT NULL`) — verify existing data first (`python manage.py makemigrations` + a data check).
3. Add a friendly `ValidationError` on duplicate tag.

**Tests:** birth without tag on an INDIVIDUAL template → error; duplicate tag → error; BATCH template without tag → OK.

**Verify:** `pytest -q apps/app_inventory/tests/test_product.py apps/app_inventory/tests/test_views_get_product_detail_view.py` + `python manage.py check`

---

## Fix 7 — Internal-client Sale clone: NO CODE CHANGE (document intentionally)

**Decision (user):** the current clone behavior in `SaleOperation.create_from_session()` is intentional and correct — the source copy is marked SOLD, the client copy is ACTIVE, so there is no double-entry/duplication error.

**Changes:**
- No code change to `apps/app_operation/models/proxies/op_sale.py`.
- Add a code comment above the `if client.is_internal:` clone block explaining the intentional SOLD/ACTIVE semantics.
- Document the behavior in `specs/operations/op_14_sale.md` (part of Fix 10 docs sync).

**Verify:** no behavior change; `pytest -q apps/app_operation/tests/operations/sale` still green.

---

## Fix 8 — Lifecycle / reversal restores ACTIVE + reversal dependency guard

**Problem:** `Product.status` is derived from the last STATUS_CHANGING operation and ignores reversals — reversing a Death/Sale/Consumption leaves status DEAD/SOLD/CONSUMED (`op_19_consumption.md` currently documents the status-remains-CONSUMED behavior). There is also no guard against reversing an operation whose output has since been consumed/moved again.

**Decision (user):** reversing Death/Sale/Consumption restores the product to ACTIVE.

**Files:**
- `apps/app_inventory/models.py` — `Product.status`
- `apps/app_operation/models/operation.py` — `reverse()`
- `specs/operations/op_17_birth.md`, `op_18_death.md`, `op_19_consumption.md`

**Changes:**
1. Make `Product.status` reversal-aware — exclude operations that have a non-reversed reversal (`reversed_by` exists), so a reversed Death/Sale/Consumption restores ACTIVE.
2. Add a reversal dependency guard: before reversing an outbound op (DEATH/CONSUMPTION/SALE), reject if the affected product has *later* non-reversed outbound movements (the product was moved again downstream).
3. Update the three op specs to the new semantics (replace the current "status remains CONSUMED" note).

**Tests:** reverse Death → status ACTIVE again; reverse a product that was later moved again → blocked; specs updated.

**Verify:** `pytest -q apps/app_operation/tests/operations/inventory apps/app_inventory`

---

## Fix 9 — Valuation: purchase-price basis (with comment for future methods)

**Problem:** no explicit valuation rule. Movement ledger value is `qty × line.unit_price`; Consumption writes off value at the line price, not original purchase cost. The "$140 remaining / $60 consumed" example has no defined rule.

**Decision (user):** value outbound movements using the purchase price (cost carried on the batch — the product's `unit_price`). Add a code comment noting other methods (moving average, FIFO) may be added later.

**Files:**
- `apps/app_inventory/models.py` — `ProductLedgerEntry.record_movement_line`, `Product.current_value`
- `apps/app_operation/models/proxies/op_consumption.py` — consumption line value
- `apps/app_operation/models/period.py` — `inventory_value_*` (align)

**Changes:**
1. Introduce a small valuation helper (single function) that returns the unit cost for an outbound movement from the product's carried `unit_price`.
2. Use it in `record_movement_line()` and for DEATH/CONSUMPTION value deltas instead of the line's entered price.
3. Add a `# NOTE: valuation method = purchase price (batch cost). Other methods (moving average, FIFO) may be added here.` comment at the helper.
4. Align `Product.current_value` and period `inventory_value_*` so consumption/COGS write-offs use the same basis.

**Tests:** purchase 100 kg @ $2, consume 30 kg → remaining 70 kg, inventory value $140, consumed value $60 (the critique's example).

**Verify:** `pytest -q apps/app_inventory/tests/test_product_ledger_entry.py apps/app_operation/tests/operations/consumption`

---

## Fix 10 — Documentation sync (operations-comparison.md + specs)

**Problem:** the comparison doc under-documents existing guards (`Product.validate_active`, `quantity > 0`, `accepts_operation`, item-total reconciliation) and omits the new guards.

**Files:**
- `specs/operations/operations-comparison.md`
- `specs/operations/op_13_purchase.md`, `op_14_sale.md`, `op_17_birth.md`, `op_18_death.md`, `op_19_consumption.md`
- `specs/features/inventory_ledger.md`

**Changes:**
1. Per-operation, add an explicit **inventory validation** line (availability, ownership, status, unit, positive qty) and an explicit **inventory effects** line (source/dest qty, ledger entry, value basis, status).
2. Document the intentional internal-client Sale clone (SOLD on source / ACTIVE on client) in `op_14_sale.md`.
3. Update the reversal-status notes in `op_17/18/19` to the new ACTIVE-restoration semantics (from Fix 8).
4. Record each implemented fix as a "Resolved" note under the Legend's `gap` marker guidance.

**Verify:** review only (markdown).

---

## Deferred / out of scope (not in this plan)

- **Physical Stock Transfer operation** — deferred; internal-client Sales already cover the intra-farm move via the intentional clone.
- **Inventory reconciliation / stocktake operation** — deferred until integration with the other operations is designed.
- **Separate approval workflow** for stock adjustments — not needed while reconciliation is deferred.

---

## Suggested implementation order

Fixes 1 → 2 → 3 (foundation guards) → 4 → 5 → 6 (smaller correctness) → 7 (comment/doc only) → 8 (lifecycle) → 9 (valuation) → 10 (docs last).

Each fix is independently testable; run the targeted tests listed under each before moving on.

---

## Implementation status (2026-08-10)

All fixes implemented and verified:

- **Fix 1 (ownership):** `InventoryMovementLine.clean()` + `_outbound_owner_entity()`; `InvoiceItemSelectForm`/`BaseInvoiceItemSelectFormSet` entity filter + ownership assertion; `Operation.inventory_owner_entity` + `save_inventory` guard; `create_inventory_movement` view casts the operation and asserts ownership; `make_product` helper accepts `entity`. Also fixed a latent `NameError` (`_` unimported) in `Operation.reverse()`.
- **Fix 2 (availability):** `InventoryMovementLine._validate_availability()` uses `ProductLedgerEntry.state_as_of`; wired into `clean()` and the auto-create path (`_auto_create_inventory_movements` now `full_clean()`s each line). SALE fresh-created products exempt.
- **Fix 3 (concurrency):** `Product.lock_ids()` (`SELECT ... FOR UPDATE`) used in the movement views, sale wizard and auto-create path; `create_payment_transaction` locks the payer fund row inside one atomic block.
- **Fix 4 (units):** quantity must be a multiple of `product_template.minimum_quantity` — enforced in `InventoryMovementLine.clean()` and `InvoiceItem.clean()`; help text clarified; the fractional arithmetic test uses a Kg template.
- **Fix 5 (closed period):** `is_date_in_closed_period()` in `period.py`; applied in `Operation.clean()`, `create_payment_transaction`, `create_repayment_transaction`, the movement view, and both adjustment views (views cast the operation so `period_entity` resolves).
- **Fix 6 (identity):** `InvoiceItemCreateForm` requires a tag for INDIVIDUAL tracking + friendly duplicate message; `Product` gains `UniqueConstraint(entity, unique_id)` (migration `0010`); dev DB checked (no duplicates) and migrated.
- **Fix 7 (clone):** no behavior change — intent comment added to `SaleOperation.create_from_session`; documented in `op_14_sale.md`.
- **Fix 8 (lifecycle):** `Product.status` is reversal-aware (excludes reversed originals + reversal clones) so reversing Death/Sale/Consumption restores ACTIVE; `Operation.reverse()` adds a reversal dependency guard; `op_17/18/19` and the consumption-reversal test updated.
- **Fix 9 (valuation):** `valuation_unit_cost()` returns the product's carried cost; `record_movement_line` uses it for outbound value deltas; test proves 100 kg @ $2 → consume 30 kg → 70 kg / $140.
- **Fix 10 (docs):** `operations-comparison.md` gains a cross-cutting inventory-guards table + updated Sale/Death/Consumption/Birth rows; `op_14/17/18/19` updated; `inventory_ledger.md` gains a valuation section.

**Deferred (per user decision):** physical Stock Transfer, reconciliation/stocktake, approval workflows.
