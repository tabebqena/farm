# Consumption — Operation Contract

**Epic:** Inventory / Livestock — One-Shot (stock event)
**Type:** Stock event (no accounting transactions), removes assets (`has_invoice=True`)
**Actions:** `create`, `reverse` (auto `move items`)
**Contract status:** v3 — Consumption is a **stock event**, not an accounting operation: it creates **no** `Transaction` rows, has no payment/settlement/repayment/adjustment machinery, and is still assigned to a financial period (and blocked inside a closed one).

> **Primary source of contract.** This document is the authoritative contract for the **Consumption** operation.
> Every clause below names its implementing code (model → mixin → view) and its pinning test — as plain names, never links, so renames do not break the spec.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> See [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md) for the shared structure and
> [`op_1_cash_injection.md`](op_1_cash_injection.md) for a fully worked example.

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.CONSUMPTION` (`"CONSUMPTION"`) | |
| Proxy class | `ConsumptionOperation` | |
| URL slug | `"consumption"` | |
| Label | `"Consumption"` | |
| Theme | `danger` / `bi-box-arrow-up-right` (inherited default) | |
| Source role | `url` (must be a Project) | |
| Destination role | `system` | |
| Registered in | `PROXY_MAP` | |
| Cross-op reference | row CO | [`operations-comparison.md`](operations-comparison.md) |

**Configuration flags**:

| Flag | Value | Meaning |
|------|-------|---------|
| `can_pay` | `False` | no payment action |
| `is_partially_payable` | `False` | n/a (no settlement) |
| `check_balance_on_payment` | `False` | n/a (no payment) |
| `has_category` / `category_required` | `False` | no financial category |
| `has_repayment` | `False` | no repayment action |
| `has_invoice` | `True` | invoice items (selected existing products) + auto inventory movements |
| `creates_assets` | `False` | links to **existing** assets; no lazy product creation |
| `is_adjustable` / `is_items_adjustable` | `False` | no accounting or item adjustments |

> **No accounting mixins.** `ConsumptionOperation` inherits only `ImmutableMixin`,
> `AmountCleanMixin`, `OfficerMixin`, `ReversableModel`, `BaseModel` (via the lean `Operation`
> base). It does **not** inherit `LinkedIssuanceTransactionMixin`, `LinkedPaymentTransactionMixin`,
> `LinkedRePaymentTransactionMixin` or `AdjustableMixin` — so no transactions, no settlement,
> no repayment, no adjustments, no COGS in `profit_loss()`.

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row names the code that must honor it (plain names, no links).

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_source`/`clean_destination` + `project` | |
| Proxy registry / URL→class resolution | |
| Shared `Operation` engine (`clean`, `save`, `reverse`, `create`, `resolve_request`, `save_inventory`, `_auto_create_inventory_movements`, reversal dependency guard, period assignment, reversable tx types) | |
| Operation type enum | |

### 2.2 Core engine (mixins / base)

| Concern | Implementing code |
|---------|-------------------|
| Immutability of `source`/`destination`/`amount`/`period` | `ImmutableMixin` + `_immutable_fields` |
| Amount must be > 0 | `AmountCleanMixin` |
| Officer must be staff + active | `OfficerMixin` |
| Reversal mechanics (clone, `reversal_of`, guards) | `ReversableModel` + `Operation.reverse()` |
| Effective amount == amount (not adjustable) | `Operation.effective_amount` (base fallback) |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| **None** — Consumption creates no `Transaction` rows | (no transaction mixins inherited) |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Fund balance never affected (no payment, no COGS) | `Entity.balance_at` (no Consumption tx types) |
| Open financial period auto-created on entity creation | `Entity.save()` |

### 2.5 Inventory layer (consumption-specific)

| Concern | Implementing code |
|---------|-------------------|
| Consumable template gating: FEED/MEDICINE nature **and** `can_be_consumed=True`; ANIMAL always rejected | (`accepts_operation`), `can_be_consumed` gating, nature allow-list |
| Product selection (existing asset, not created) — `InvoiceItemSelectFormSet` | + `_build_formset` |
| Ownership guard: selected product belongs to the source project | `save_inventory` + `InventoryMovementLine.clean` |
| Availability guard: quantity ≤ physically-present on-hand (movement-ledger) | `_validate_availability` + `InventoryMovementLine.clean` |
| Unit consistency: quantity multiple of `product_template.minimum_quantity` | `InventoryMovementLine.clean` |
| Auto outbound movement lines; product status ACTIVE while partial on-hand remains, CONSUMED once fully written off (net presence 0); restored to ACTIVE on reversal | `Product.status` |
| Movement-based valuation (`movement_state`, `inventory_value`) — consumed value leaves inventory **once**; the movement line **is** the ledger (no separate `ProductLedgerEntry` table) | `inventory_value`, `_OUTBOUND_TYPES` |
| Reversal dependency guard (products moved again later) | `Operation.reverse()` |

### 2.6 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (generic — resolves the project URL source + system destination, builds the select formset) | `OperationCreateView` |
| POST parsing/validation | `OperationDataValidator` |
| Quick-consume view (one-step from stock detail) | `quick_consume` |
| Reverse view (reason required) | `operation_reverse_view` |
| Detail view (aggregate amount + movement lines + reversal action; no payment/settlement UI) | `operation_detail_view` |
| URL: `/<pk>/<op_type>/create` (op_type = `consumption`) | |
| URL: `entity/<int:entity_pk>/stock/consume/` (name `quick_consume`) | |
| URL: `/<pk>/reverse/` | |
| URL: `/<pk>/detail/` | |
| Templates | |

### 2.7 Tests

| Concern | Test file |
|---------|-----------|
| Create branches (movement lines, status, no transactions, period assigned, non-cash) | `test_consumption_consumption_create` (`ConsumptionCreateTest` + `ConsumptionCreateValidationTest`) |
| Reverse branches (reversal record, no counter-tx, auto lines reversed, ledger negation, status CONSUMED→ACTIVE, VR1/VR2/VR4, SR10) | `test_consumption_consumption_reversal` (`ConsumptionReversalTest`) |
| Stock detail/history UI branches | `test_consumption_stock_detail` (`ConsumptionStockDetailTest`) |
| One-step quick-consume branches | `test_quick_consume_from_stock` (`QuickConsumeFromStockTest`) |
| Coverage manifest (executable branch registry) | `test_coverage_manifest` → `base.py` `COVERAGE_MANIFEST` |

---

## 3. Money flow & entities

- **Source (role):** the **Project** entity in the URL (`is_project=True`). It owns the consumed asset.
- **Destination (role):** the single **System** entity (`is_system=True`). Virtual.
- **No transactions are created.** A consumption removes the consumed asset's value **exactly once**, via movement-based inventory value (`inventory_value()`). The project's fund balance, payables and receivables are **never** affected, and `profit_loss()` is **not** reduced (no COGS).

---

## 4. Settlement model

There is **no settlement model** — Consumption does not inherit the payment/settlement machinery.
`amount_settled`, `is_fully_settled`, `amount_remaining_to_settle`, `payment_transactions` do
**not** exist on a `ConsumptionOperation`. The operation's value lives in inventory.

---

## 5. Actions

### 5.1 `create`

Entry points: model `ConsumptionOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()`, then the invoice formset → `save_inventory()` → `_auto_create_inventory_movements()`.

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source is Project | `source.is_project` | `ValidationError` | `"Consumption source must be a Project entity."` | `clean_source` | `test_source_must_be_a_project_entity` / `test_source_system_entity_raises_validation_error` (`ConsumptionCreateValidationTest`) — mirror of [`op_18`](op_18_death.md) VC1 |
| VC2 | Destination is System | `destination.is_system` | `ValidationError` | `"Consumption destination must be the System entity."` | `clean_destination` | `test_destination_must_be_system_entity` / `test_destination_person_entity_raises_validation_error` (`ConsumptionCreateValidationTest`) — mirror of [`op_18`](op_18_death.md) VC2 |
| VC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | `Operation.clean()` | shared engine suite |
| VC4 | Destination entity active | `destination.active` | `ValidationError` | same as VC3 | `Operation.clean()` | shared engine suite |
| VC5 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | shared engine suite |
| VC6 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | `OfficerMixin` | (view), shared engine suite (model) |
| VC7 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | `OfficerMixin` | shared engine suite |
| VC8 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | `Operation.clean()` | period suite |
| VC9 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | `Operation.save()` | period suite |
| VC10 | Template is consumable | `nature ∈ {FEED, MEDICINE}` **and** `can_be_consumed=True` (ANIMAL is always rejected — `can_be_consumed` forced off) | `ValidationError` | template rejected by `accepts_operation(CONSUMPTION)` | `ProductTemplate.accepts_operation` + nature allow-list | `test_non_consumable_template_rejected_for_consumption` (ANIMAL) / `test_non_consumable_flag_rejected_for_consumption` (FEED `can_be_consumed=False`) — `ConsumptionCreateTest` |
| VC11 | Product linked (must be an existing asset) | `selected_product` present on the invoice item | form/`ValidationError` | missing-product error | `InvoiceItemSelectFormSet` + `save_inventory` | implied by create flow |
| VC12 | Ownership — product belongs to source project | `selected.entity == inventory_owner_entity` | `ValidationError` | `"Product '%(p)s' does not belong to '%(entity)s' and cannot be used in this operation."` | `save_inventory` + `InventoryMovementLine.clean` | shared inventory suite |
| VC13 | Availability — quantity ≤ on-hand | `quantity ≤ movement_state(product, as_of=date)["quantity"]` | `ValidationError` | availability error | `InventoryMovementLine.clean` + `_auto_create_inventory_movements` | shared inventory suite |
| VC14 | Unit consistency | quantity is a multiple of `product_template.minimum_quantity` | `ValidationError` | unit-step error | `InventoryMovementLine.clean` | shared inventory suite |
| VC15 | Product not already terminal | `Product.status` is not CONSUMED/SOLD/DEAD/REMOVED (unless reversal/adjustment) | `ValidationError` | `"Product '%(id)s' has status %(status)s and cannot be used in new operations."` | `Product.validate_active` | |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | No transactions created | `get_all_transactions().count() == 0` (no issuance, no payment) | (no transaction mixins) | |
| SC2 | No settlement machinery | `amount_settled`/`is_fully_settled`/`create_payment_transaction` absent | (no payment mixin) | |
| SC3 | No cash flow / fund unchanged | `balance_at()` unaffected by consumption (no payment, no COGS) | `Entity.balance_at` | |
| SC4 | Auto outbound movement lines | one movement line per item at item qty (shared `group_key`), linked to the selected product, valued at the product's carried cost | `_auto_create_inventory_movements` | |
| SC5 | Product status: ACTIVE → CONSUMED at zero on-hand | the consumed product's movement-based `status` derives from the net movement presence: while the remaining on-hand quantity is `> 0` (partial consumption, e.g. 2 of 5) the product stays **ACTIVE**; once the net quantity reaches `0` (fully consumed) the status becomes **CONSUMED**. Physically moved (not obligated-only) | `Product.status` | |
| SC6 | Inventory value drops once | `inventory_value()` decreases by the carried cost (net presence → 0) | `movement_state` + `inventory_value` | |
| SC7 | Period auto-assigned | `period` = the project's covering period (open period auto-created at entity creation) | `Operation.save()` + `Entity.save()` | covered by period suite |
| SC8 | profit_loss unchanged | consumption is not an accounting transaction → `profit_loss()` is unaffected | `Entity.profit_loss` | |

#### 5.1.3 `quick-consume` from stock (one-step shortcut)

A lightweight entry point on the stock detail page that removes the friction of the full consumption form for daily feeding: pick the product and a quantity, click **Consume**, and the whole pipeline runs in one POST.

- View: `quick_consume()` — POSTs a minimal form (`product_id`, `quantity`, `unit_price`, optional `date`/`description`), builds the single-item formset internally, and delegates to the unchanged `ConsumptionOperation.create(...)` factory — so the auto movement line and the CONSUMED product status reuse the proven path (SC1–SC8). No transactions are created.
- Route: `entity/<int:entity_pk>/stock/consume/` (name `quick_consume`).
- Guards are checked in the view for a friendly message **and again at the model layer** via `InventoryMovementLine.clean()` / `save_inventory()`:

| # | Guard | Pass condition | Friendly message (view) | Enforced by | Pinned by test |
|---|-------|----------------|-------------------------|-------------|----------------|
| QC1 | Officer | `request.user.is_staff` | `"You must be an officer to consume from stock."` | `quick_consume` | |
| QC2 | Ownership | `product.entity == entity` | `"Product does not belong to this stock."` | `quick_consume` | |
| QC3 | Consumable nature + flag | `product_template.accepts_operation(CONSUMPTION)` (FEED/MEDICINE + `can_be_consumed`) | `"'%(name)s' cannot be consumed."` | `quick_consume` | |
| QC4 | Quantity > 0 | `quantity > 0` | `"Quantity must be greater than zero."` | `quick_consume` | structural (mirror of VC5 at line level) |
| QC5 | Availability | `quantity ≤ movement_state(product, as_of=date)["quantity"]` | `"Insufficient stock: %(qty)s requested but only %(avail)s available."` | `quick_consume` | |
| QC6 | Unit consistency | quantity multiple of `minimum_quantity` | `"Quantity %(qty)s must be a multiple of the minimum increment %(min)s."` | `quick_consume` | shared inventory suite |
| QC7 | Date parseable | optional `date` field is a valid date | `"Invalid date format."` | `quick_consume` | structural |
| QC8 | System entity available | a System entity exists (or is created) | — | `quick_consume` | structural |

- Redirects back to the stock detail page on success or error (Django message). The success path and the partial-consumption path are covered by the quick-consume tests (see §10).

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | `ReversableModel._validate_can_be_reversed` + view guard | shared engine suite (cf. [`op_1`](op_1_cash_injection.md) VR1) |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | `ReversableModel._validate_can_be_reversed` + view guard | shared engine suite |
| VR3 | No non-reversed adjustments | n/a — Consumption is not adjustable | never fails | — | `is_adjustable=False` | n/a |
| VR4 | Reversal dependency guard | none of the consumed products were moved again in a later non-reversed outbound op (SALE/DEATH/CONSUMPTION) | `ValidationError` | `"Cannot reverse this operation: its products were moved again in a later operation."` | `Operation.reverse()` | pinned by `test_reversal_blocked_when_product_moved_again_in_later_consumption` (`ConsumptionReversalTest`) — partial consumption then full write-off |
| VR5 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | `operation_reverse_view` | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | `ReversableModel.reverse()` | |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | `ReversableModel.reverse()` | structural (same engine as [`op_1`](op_1_cash_injection.md) SR2) |
| SR3 | Reversal inherits identity | `amount`, `source`, `destination` copied | `ReversableModel._get_reverse_kwargs` | structural (same engine as [`op_1`](op_1_cash_injection.md) SR3) |
| SR4 | No counter-transactions | neither the original nor its reversal owns any `Transaction` | (no transaction mixins) | |
| SR5 | Auto movement lines reversed | one reversal line per original (equal qty, `reversal_of` link, same product); originals preserved | `Operation.reverse()` → `line.reverse()` | |
| SR6 | Ledger negated | the consumed product's net presence restored to its pre-consumption on-hand (`qty`/`value` back to baseline) | `movement_state` | |
| SR7 | Product status restored to ACTIVE | reversal-aware `Product.status` → `ACTIVE` (reversal operations are excluded from the status derivation) | `Product.status` | |
| SR8 | profit_loss unchanged | reversal does not touch `profit_loss()` | `Entity.profit_loss` | |
| SR9 | Fund balance unchanged | neither the consumption nor its reversal affects `balance_at()` | `Entity.balance_at` | |
| SR10 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger, inventory value) | whole engine | shared engine invariant |

### 5.3 `pay`

There is **no pay action** for Consumption — it has no payment machinery at all
(`create_payment_transaction` does not exist on the class). Payment-related code is never
reachable.

### 5.4 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by `ImmutableMixin` via `_immutable_fields`. Shared with every operation (see [`op_1`](op_1_cash_injection.md) §5.4).

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — `Entity.save()`.
- The operation's governing entity (`period_entity`) is the **source project** (`_source_role = "url"`) — `Operation.period_entity`. The System (virtual) has no periods and is exempt.
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC9).
- New operations dated inside a **closed** period are rejected (VC8).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period (`_reverse_period`).

---

## 7. Entity roles & balance contract

- Project is the only allowed source; System the only allowed destination — enforced at model (VC1/VC2).
- No transactions → the project's fund balance, payables and receivables are **never** affected by a consumption.
- The consumed asset's value leaves **exactly once**, via movement-based inventory value (`inventory_value()`); `FinancialPeriod.end_assets` = cash + movement-based inventory + loans + advances, so a consumption reduces `end_assets` exactly once, via inventory.

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Create route | `POST/GET /<project_pk>/consumption/create` → `OperationCreateView` (generic; resolves the proxy via the `op_type` URL segment) |
| Source selection | the **Project** from the URL (`_source_role="url"`); no picker |
| Destination selection | locked to the single **System** entity (`_dest_role="system"`); no secondary-entity field |
| Category | hidden (no category) |
| Amount | computed from item totals (Σ quantity × unit_price) via `_compute_amount`; validated > 0 at model |
| Invoice items | `InvoiceItemSelectFormSet` (`creates_assets=False` → `_build_formset`) — one row per affected product, picking an **existing** product (`selected_product`) owned by the project |
| Consumable product | selectable products are those whose template is FEED/MEDICINE **and** `can_be_consumed=True` (`accepts_operation(CONSUMPTION)`); ANIMAL templates are never selectable — **TODO**: the full create form's `InvoiceItemSelectFormSet` currently filters `selected_product` by ownership only, so ANIMAL / non-consumable FEED products still appear in the dropdown (rejected only on submit via `InvoiceItem.clean()`); restrict the queryset by consumability (mirror the `quick_consume` guard) |
| POST parsing | `OperationDataValidator` — date format, description, category (n/a), `amount_paid` (n/a, forced 0) |
| Quick-consume | stock detail `live` tab renders an inline form posting to `entity/<entity_pk>/stock/consume/` (name `quick_consume`) — see §5.1.3; redirects back to stock detail with a Django message |
| List entry | "Consumption" link |
| Detail | `operation_detail_view` — shows the operation total + auto movement lines + reversal action; **no** payment/settlement sections (rendered as one-shot) |
| Stock history | the consumed product's OUT movement appears on the Stock History page (`stock_history`); the `live` tab excludes CONSUMED products (`stock_detail`) |
| Reverse | `operation_reverse_view` — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

> **TODO (open gap):** the "Consumable product" row above is not fully implemented for the **full create form** path. `InvoiceItemSelectFormSet` restricts `selected_product` to the owning project only; the FEED/MEDICINE + `can_be_consumed` restriction is enforced at the model layer (`InvoiceItem.clean()` → `accepts_operation(CONSUMPTION)`), so invalid picks fail on submit rather than being unselectable. See the `TODO(consumption)` marker in `InvoiceItemSelectForm.__init__`. (The `quick_consume` shortcut — QC3 — already gates the selectable product correctly.)

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source=project · VC2 dest=system · VC3 source active · VC4 dest active · VC5 amount>0 · VC6 officer staff · VC7 officer active · VC8 not closed-period · VC9 covering period exists · VC10 consumable FEED/MEDICINE (`can_be_consumed`) · VC11 product linked · VC12 ownership · VC13 availability ≤ on-hand · VC14 unit multiple · VC15 product not terminal

**create — effects:** SC1 no transactions · SC2 no settlement machinery · SC3 no cash flow / fund unchanged · SC4 auto outbound lines · SC5 status ACTIVE/CONSUMED · SC6 inventory value ▼ once · SC7 period assigned · SC8 profit_loss unchanged

**quick-consume — guards:** QC1 officer staff · QC2 ownership · QC3 consumable nature + flag · QC4 quantity > 0 · QC5 availability ≤ on-hand · QC6 unit multiple · QC7 date parseable · QC8 system entity present

**quick-consume — effects:** QCS1 delegates to `ConsumptionOperation.create(...)` → SC1–SC8 full pipeline in one POST

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no adjustments (n/a) · VR4 reversal dependency guard · VR5 reason required (view)

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 identity copied · SR4 no counter-txs · SR5 auto lines reversed · SR6 ledger negated · SR7 status restored to ACTIVE · SR8 profit_loss unchanged · SR9 fund balance unchanged · SR10 differential invariant

**immutability:** IM1/IM2/IM3 source/destination/amount immutable

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| Auto movement line | | SC4, VC11 |
| Ledger / stock state | | SC6 |
| Status: ACTIVE while partial → CONSUMED at zero | `test_partial_consumption_keeps_product_active` (partial → ACTIVE) + `test_create_marks_product_consumed` (zero → CONSUMED) | SC5 |
| Status reuse blocked | `test_consumed_product_validate_active_blocks_reuse` | VC15 |
| No transactions | `test_create_creates_no_transactions` | SC1 |
| No settlement machinery | `test_period_is_assigned_and_no_settlement_machinery` | SC2 |
| No cash flow / fund unchanged | `test_create_does_not_drain_fund_balance` | SC3 |
| profit_loss unchanged | `test_create_does_not_change_profit_loss` | SC8 |
| Period assigned | `test_period_is_assigned_and_no_settlement_machinery` | SC7 |
| Reverse happy path | `test_reverse_creates_reversal_record` | SR1 |
| Auto lines reversed | `test_reverse_reverses_auto_movement_lines` | SR5, SR6 |
| Ledger negation | `test_reverse_negates_ledger_entries` | SR6 |
| No counter txs | `test_reverse_creates_no_transactions` | SR4 |
| Status restored ACTIVE | `test_reversed_product_returns_to_active_status` | SR7 |
| Reversal dependency guard | pinned by `test_reversal_blocked_when_product_moved_again_in_later_consumption` | VR4 |
| Already reversed / is-a-reversal | `test_cannot_reverse_already_reversed_operation` / `test_cannot_reverse_a_reversal` | VR1, VR2 |
| Differential invariant (create + reverse unchanged) | `test_create_then_reverse_leaves_world_unchanged` | SR10 |
| Source role (model clean) | `test_source_must_be_a_project_entity` | VC1 |
| Destination role (model clean) | `test_destination_must_be_system_entity` | VC2 |
| Template gating (full create pipeline) | `test_non_consumable_template_rejected_for_consumption` / `test_non_consumable_flag_rejected_for_consumption` | VC10 |
| Stock history shows OUT | | SC4, SC5 (UI) |
| Live tab excludes consumed | | SC5 (UI) |
| Quick-consume full pipeline | | QCS1, SC1–SC8 |
| Quick-consume form renders | | QC (UI) |
| Quick-consume partial | | QCS1 (partial) |
| Quick-consume availability | | QC5, VC13 |
| Quick-consume officer | | QC1, VC6 |
| Quick-consume nature | | QC3, VC10 |
| Quick-consume ownership | | QC2, VC12 |
