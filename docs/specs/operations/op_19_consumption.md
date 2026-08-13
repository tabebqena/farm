# Consumption — Operation Contract

**Epic:** Inventory / Livestock — One-Shot
**Type:** One-shot, auto-settled, removes assets (`has_invoice=True`)
**Actions:** `create`, `reverse` (auto `move items`)
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Consumption** operation.
> Every clause below is registered to its implementing code (model → mixin → transaction → view) and to its pinning test.
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
| `_issuance_transaction_type` | `CONSUMPTION_ISSUANCE` | issuance tx created on save |
| `_payment_transaction_type` | `CONSUMPTION_PAYMENT` | payment tx created on save (one-shot) — **non-cash bookkeeping** |
| `_is_one_shot_operation` | `True` | payment fires at create; no standalone pay action |
| `can_pay` | `False` | `process_payment()` is a no-op |
| `is_partially_payable` | `False` | payment must equal amount (one-shot) |
| `max_payment_transaction_count` | `1` | exactly one payment tx ever |
| `check_balance_on_payment` | `False` | write-off — no fund-balance check at create |
| `has_category` / `category_required` | `False` | no financial category |
| `has_repayment` | `False` | no repayment action |
| `has_invoice` | `True` | invoice items (selected existing products) + auto inventory movements |
| `creates_assets` | `False` | links to **existing** assets; no lazy product creation |
| `is_adjustable` / `is_items_adjustable` | `False` (inherited) | no accounting or item adjustments |

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row links the clause to the code that must honor it.

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_source`/`clean_destination` + payment funds + `project` | |
| Proxy registry / URL→class resolution | |
| Shared `Operation` engine (`clean`, `save`, `reverse`, `create`, `resolve_request`, `save_inventory`, `_auto_create_inventory_movements`, reversal dependency guard, period assignment, reversable tx types) | |
| Operation type enum | |

### 2.2 Core engine (mixins / base)

| Concern | Implementing code |
|---------|-------------------|
| Immutability of `source`/`destination`/`amount`/`period` | `ImmutableMixin` + `_immutable_fields` |
| Amount must be > 0 | `AmountCleanMixin` |
| Officer must be staff + active | `OfficerMixin` |
| Source fund exists + active | `SourceFundMixin` |
| Target fund exists + active | `TargetFundMixin` |
| Issuance tx creation on save | `LinkedIssuanceTransactionMixin` |
| One-shot payment tx creation + settlement (`amount_settled`, `is_fully_settled`) | `LinkedPaymentTransactionMixin` |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | `ReversableModel` + `Operation.reverse()` |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | |
| `CONSUMPTION_ISSUANCE` (project → system, no balance) | |
| `CONSUMPTION_PAYMENT` (project → system, **non-cash — excluded from `payment_types()`**) | |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Balance derivation (payment types only — `CONSUMPTION_PAYMENT` excluded, so consumption never drains a fund balance) | `Entity.balance_at` |
| COGS in P&L (`CONSUMPTION_ISSUANCE` counted as a cost; its reversal offset restores profit) | `Entity.profit_loss` |
| Virtual/system-entity payment exemption | `Entity.can_pay` |
| Open financial period auto-created on entity creation | `Entity.save()` |
| Period `end_assets` = cash + movement-based inventory + loans + advances (consumption leaves via inventory, not cash) | `FinancialPeriod.end_assets` |

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
| Detail view (aggregate amount + movement lines + reversal action; per-transaction list hidden — one-shot) | `operation_detail_view` |
| URL: `/<pk>/<op_type>/create` (op_type = `consumption`) | |
| URL: `entity/<int:entity_pk>/stock/consume/` (name `quick_consume`) | |
| URL: `/<pk>/reverse/` | |
| URL: `/<pk>/detail/` | |
| Templates | |

### 2.7 Tests

| Concern | Test file |
|---------|-----------|
| Create branches (movement lines, status, tx, settlement, COGS, non-cash) | |
| Reverse branches (reversal record, counter-tx, auto lines reversed, ledger negation, status CONSUMED→ACTIVE, COGS negated) | |
| Stock detail/history UI branches | |
| One-step quick-consume branches | |
| Coverage manifest (executable branch registry) | |

---

## 3. Money flow & entities

- **Source (payer):** the **Project** entity in the URL (`is_project=True`). Its fund is the source fund; the project owns the consumed asset.
- **Destination (receiver):** the single **System** entity (`is_system=True`). Virtual — never balance-checked, exempt from fund-balance validation (`payment_target_fund`).
- **Transaction flow** (both on create, project → system):

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `CONSUMPTION_ISSUANCE` | `project.fund → system.fund` | none (issuance, not a payment type) |
| 2 | `CONSUMPTION_PAYMENT` | `project.fund → system.fund` | **none** — non-cash bookkeeping, **excluded from `payment_types()`** |

- **Payment source fund:** `self.source` (project)
- **Payment target fund:** `self.destination` (system)
> **No cash flow — COGS (Option B).** Consumed feed/medicine is recognized as **Cost of Goods Sold (COGS)** that reduces the project's own profit in the period it is consumed — matching the feed cost to the period of the milk/meat revenue it helps produce.
> - `CONSUMPTION_ISSUANCE` is counted in `Entity.profit_loss()` costs, so the P&L and `FinancialPeriod.amount` reflect consumed feed/medicine in the consumption period.
> - `CONSUMPTION_PAYMENT` is **not** a payment type anymore (removed from `TransactionType.payment_types()`), so consumption does **not** drain the fund balance (`balance_at()` is unchanged). The consumed value moves from the inventory asset (movement ledger) to COGS on the P&L — a clean internal transfer on the project's books.
> - `end_assets` (cash balance + remaining inventory) and the P&L both reflect consumption **exactly once**.
> - Reversal of a consumption negates the COGS: the reversal issuance restores profit and keeps the fund balance unchanged.

---

## 4. Settlement model

Derived from `LinkedPaymentTransactionMixin` using payment-type transactions only (note: `CONSUMPTION_PAYMENT` is **not** a payment type for balance purposes, but it *is* the one-shot settlement transaction for this operation):

| Property | After create | After reverse |
|----------|--------------|---------------|
| `amount_settled` | `== amount` | `0.00` |
| `total_settlable_amount` (`effective_amount`) | `== amount` (no adjustments) | unchanged |
| `amount_remaining_to_settle` | `0.00` | `== amount` |
| `is_fully_settled` | `True` | `False` |

Because the operation is one-shot and never adjustable, settlement is **immediate and terminal** — there is no standalone `pay` action.

---

## 5. Actions

### 5.1 `create`

Entry points: model `ConsumptionOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx, then payment tx), then the invoice formset → `save_inventory()` → `_auto_create_inventory_movements()`.

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source is Project | `source.is_project` | `ValidationError` | `"Consumption source must be a Project entity."` | `clean_source` | model clean (mirror of [`op_18`](op_18_death.md) VC1) |
| VC2 | Destination is System | `destination.is_system` | `ValidationError` | `"Consumption destination must be the System entity."` | `clean_destination` | model clean (mirror of [`op_18`](op_18_death.md) VC2) |
| VC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | `Operation.clean()` | shared engine suite |
| VC4 | Destination entity active | `destination.active` | `ValidationError` | same as VC3 | `Operation.clean()` | shared engine suite |
| VC5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | `SourceFundMixin` | shared engine suite |
| VC6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | `TargetFundMixin` | shared engine suite |
| VC7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | shared engine suite |
| VC8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | `OfficerMixin` | (view), shared engine suite (model) |
| VC9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | `OfficerMixin` | shared engine suite |
| VC10 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | `Operation.clean()` | period suite |
| VC11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | `Operation.save()` | period suite |
| VC12 | Balance exempt (write-off) | no balance check | never fails | — | `check_balance_on_payment=False` | structural (`can_pay`-less one-shot) |
| VC13 | Tx entity-type contract | `source.is_project` and `target.is_system` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | `Transaction.create()` | implied by VC1/VC2 (model clean blocks first) |
| VC14 | Tx operation-type allowed | document is `CONSUMPTION` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | `Transaction.create()` | implied by VC1/VC2 |
| VC15 | Source ≠ target | project ≠ system | always true | `"Source and target funds must be different."` | `Transaction.clean()` | structural (project ≠ system) |
| VC16 | Template is consumable | `nature ∈ {FEED, MEDICINE}` **and** `can_be_consumed=True` (ANIMAL is always rejected — `can_be_consumed` forced off) | `ValidationError` | template rejected by `accepts_operation(CONSUMPTION)` | `ProductTemplate.accepts_operation` + nature allow-list | |
| VC17 | Product linked (must be an existing asset) | `selected_product` present on the invoice item | form/`ValidationError` | missing-product error | `InvoiceItemSelectFormSet` + `save_inventory` | implied by create flow |
| VC18 | Ownership — product belongs to source project | `selected.entity == inventory_owner_entity` | `ValidationError` | `"Product '%(p)s' does not belong to '%(entity)s' and cannot be used in this operation."` | `save_inventory` + `InventoryMovementLine.clean` | shared inventory suite |
| VC19 | Availability — quantity ≤ on-hand | `quantity ≤ movement_state(product, as_of=date)["quantity"]` | `ValidationError` | availability error | `InventoryMovementLine.clean` + `_auto_create_inventory_movements` | shared inventory suite |
| VC20 | Unit consistency | quantity is a multiple of `product_template.minimum_quantity` | `ValidationError` | unit-step error | `InventoryMovementLine.clean` | shared inventory suite |
| VC21 | Product not already terminal | `Product.status` is not CONSUMED/SOLD/DEAD/REMOVED (unless reversal/adjustment) | `ValidationError` | `"Product '%(id)s' has status %(status)s and cannot be used in new operations."` | `Product.validate_active` | |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | 1 × `CONSUMPTION_ISSUANCE`, amount `== op.amount`, `project → system` | `LinkedIssuanceTransactionMixin.save()` | |
| SC2 | Payment tx created (non-cash) | 1 × `CONSUMPTION_PAYMENT`, amount `== op.amount`, `project → system`; **not** a `payment_types()` type → no balance/payable/receivable effect | `LinkedPaymentTransactionMixin.save()` | same as SC1 |
| SC3 | Tx amounts equal op amount | both txs `amount == op.amount` (amount = Σ item quantity × unit_price) | `_compute_amount` + transaction creation | |
| SC4 | Tx fund direction | both txs `source=project`, `target=system` | | same as SC1 |
| SC5 | Fully settled immediately | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | `LinkedPaymentTransactionMixin` | |
| SC6 | No cash flow | project fund balance unchanged (payment non-cash); system (virtual) ▲ in bookkeeping only | `payment_types()` exclusion + `Entity.balance_at` | |
| SC7 | Auto outbound movement lines | one movement line per item at item qty (shared `group_key`), linked to the selected product, valued at the product's carried cost | `_auto_create_inventory_movements` | |
| SC8 | Product status: ACTIVE → CONSUMED at zero on-hand | the consumed product's movement-based `status` derives from the net movement presence: while the remaining on-hand quantity is `> 0` (partial consumption, e.g. 2 of 5) the product stays **ACTIVE**; once the net quantity reaches `0` (fully consumed) the status becomes **CONSUMED**. Physically moved (not obligated-only) | `Product.status` | |
| SC9 | COGS — P&L reduced | `CONSUMPTION_ISSUANCE` counted in `profit_loss()` costs → `Entity.profit_loss()` drops by the consumed value in the consumption period; inventory value leaves **once** via `movement_state` (net presence → 0) | `Entity.profit_loss` + `movement_state` | |
| SC10 | Period auto-assigned | `period` = the project's covering period (open period auto-created at entity creation) | `Operation.save()` + `Entity.save()` | covered by period suite |

#### 5.1.3 `quick-consume` from stock (one-step shortcut)

A lightweight entry point on the stock detail page that removes the friction of the full consumption form for daily feeding: pick the product and a quantity, click **Consume**, and the whole pipeline runs in one POST.

- View: `quick_consume()` — POSTs a minimal form (`product_id`, `quantity`, `unit_price`, optional `date`/`description`), builds the single-item formset internally, and delegates to the unchanged `ConsumptionOperation.create(...)` factory — so issuance + payment transactions, the auto movement line, and the CONSUMED product status all reuse the proven path (SC1–SC10).
- Route: `entity/<int:entity_pk>/stock/consume/` (name `quick_consume`).
- Guards are checked in the view for a friendly message **and again at the model layer** via `InventoryMovementLine.clean()` / `save_inventory()`:

| # | Guard | Pass condition | Friendly message (view) | Enforced by | Pinned by test |
|---|-------|----------------|-------------------------|-------------|----------------|
| QC1 | Officer | `request.user.is_staff` | `"You must be an officer to consume from stock."` | `quick_consume` | |
| QC2 | Ownership | `product.entity == entity` | `"Product does not belong to this stock."` | `quick_consume` | |
| QC3 | Consumable nature + flag | `product_template.accepts_operation(CONSUMPTION)` (FEED/MEDICINE + `can_be_consumed`) | `"'%(name)s' cannot be consumed."` | `quick_consume` | |
| QC4 | Quantity > 0 | `quantity > 0` | `"Quantity must be greater than zero."` | `quick_consume` | structural (mirror of VC7 at line level) |
| QC5 | Availability | `quantity ≤ movement_state(product, as_of=date)["quantity"]` | `"Insufficient stock: %(qty)s requested but only %(avail)s available."` | `quick_consume` | |
| QC6 | Unit consistency | quantity multiple of `minimum_quantity` | `"Quantity %(qty)s must be a multiple of the minimum increment %(min)s."` | `quick_consume` | shared inventory suite |
| QC7 | Date parseable | optional `date` field is a valid date | `"Invalid date format."` | `quick_consume` | structural |
| QC8 | System entity available | a System entity exists (or is created) | — | `quick_consume` | structural |

- Redirects back to the stock detail page on success or error (Django message). Success path verified by; partial consumption by.

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | `ReversableModel._validate_can_be_reversed` + view guard | shared engine suite (cf. [`op_1`](op_1_cash_injection.md) VR1) |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | `ReversableModel._validate_can_be_reversed` + view guard | shared engine suite |
| VR3 | No explicit txs to reverse | all txs are implicit (one-shot issuance + payment) | `ValidationError` (would require manual reversal) | `"You can't reverse this object as it has non-reversed transactions…"` | `ReversableModel._requires_transaction_reversal` + `Operation._implicit_reversable_transaction_types` | implied by successful reverse |
| VR4 | Reversal dependency guard | none of the consumed products were moved again in a later non-reversed outbound op (SALE/DEATH/CONSUMPTION) | `ValidationError` | `"Cannot reverse this operation: its products were moved again in a later operation."` | `Operation.reverse()` | shared outbound-op suite (SALE/DEATH/CONSUMPTION) — **consumption-focused test pending** |
| VR5 | No non-reversed adjustments | n/a — Consumption is not adjustable | never fails | — | `is_adjustable=False` | n/a |
| VR6 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | `operation_reverse_view` | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | `ReversableModel.reverse()` | |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | `ReversableModel.reverse()` | structural (same engine as [`op_1`](op_1_cash_injection.md) SR2) |
| SR3 | Reversal inherits identity | `amount`, `source`, `destination` copied | `ReversableModel._get_reverse_kwargs` | structural (same engine as [`op_1`](op_1_cash_injection.md) SR3) |
| SR4 | Counter-tx for issuance | `system → project`, same amount, same type, `reversal_of=original` | `Transaction.reverse()` | |
| SR5 | Counter-tx for payment | `system → project`, same amount, same type, `reversal_of=original` | same as SR4 | same as SR4 |
| SR6 | Counter-txs preserve type + amount | `counter.type == original.type`, `counter.amount == original.amount` | same as SR4 | same as SR4 |
| SR7 | Auto movement lines reversed | one reversal line per original (equal qty, `reversal_of` link, same product); originals preserved | `Operation.reverse()` → `line.reverse()` | |
| SR8 | Ledger negated | the consumed product's net presence restored to its pre-consumption on-hand (`qty`/`value` back to baseline) | `movement_state` | |
| SR9 | Product status restored to ACTIVE | reversal-aware `Product.status` → `ACTIVE` (reversal operations are excluded from the status derivation) | `Product.status` | |
| SR10 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | `LinkedIssuanceTransactionMixin.save()` | shared engine (cf. [`op_1`](op_1_cash_injection.md) SR7) |
| SR11 | COGS negated — P&L restored | the reversal `CONSUMPTION_ISSUANCE` is a mirror tx (`target=fund`, `reversal_of` set) that `profit_loss()` negates → profit returns to pre-consumption baseline | `Entity.profit_loss` | |
| SR12 | Fund balance unchanged | neither the consumption nor its reversal is a payment type → `balance_at()` unchanged throughout | `payment_types()` exclusion + `Entity.balance_at` | |
| SR13 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger, inventory value, P&L) | whole engine | shared engine invariant |

### 5.3 `pay` (one-shot guard)

There is **no standalone pay action** for Consumption:

| Branch | Behavior | Enforced by | Pinned by test |
|--------|----------|-------------|----------------|
| `process_payment()` called | no-op (returns immediately — `can_pay=False`) | `process_payment` | n/a (covered by `can_pay=False`) |
| `create_payment_transaction()` called after create | `ValidationError` — one-shot allows a single payment only, amount must equal `op.amount` | `create_payment_transaction` | shared one-shot suite (cf. [`op_1`](op_1_cash_injection.md) BP2) |

### 5.4 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by `ImmutableMixin` via `_immutable_fields`. Shared with every operation (see [`op_1`](op_1_cash_injection.md) §5.4).

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — `Entity.save()`.
- The operation's governing entity (`period_entity`) is the **source project** (`_source_role = "url"`) — `Operation.period_entity`. The System (virtual) has no periods and is exempt.
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC11).
- New operations dated inside a **closed** period are rejected (VC10).
- `FinancialPeriod.amount` (closed project periods) is driven by the same issuance-based P&L, so consumed feed/medicine lands as COGS in the consumption period (`FinancialPeriod.amount`).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period (`_reverse_period`).

---

## 7. Entity roles & balance contract

- Project is the only allowed source; System the only allowed destination — enforced at model (VC1/VC2) and transaction (VC13) layers.
- `CONSUMPTION_PAYMENT` is **deliberately excluded** from `payment_types()` — it is a non-cash bookkeeping record. The project's fund balance, payables and receivables are **never** affected by a consumption.
- The consumed asset's value is recognized **exactly once**, as **COGS** in `Entity.profit_loss()`: `CONSUMPTION_ISSUANCE` is a cost (source=fund), and its reversal (target=fund, `reversal_of` set) is negated to restore profit (SC9/SR11). The movement-based `inventory_value()` drops by the carried cost at the same time.
- `FinancialPeriod.end_assets` = cash + movement-based inventory + loans + advances, so a consumption reduces `end_assets` exactly once, via inventory (not cash) — and the P&L counts it once as COGS.
- System is **virtual**: `can_pay` always returns `True`, so consumptions are never blocked by fund balance (VC12).

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
| Consumable product | selectable products are those whose template is FEED/MEDICINE **and** `can_be_consumed=True` (`accepts_operation(CONSUMPTION)`); ANIMAL templates are never selectable |
| POST parsing | `OperationDataValidator` — date format, description, category (n/a), `amount_paid` (n/a, forced 0) |
| Quick-consume | stock detail `live` tab renders an inline form posting to `entity/<entity_pk>/stock/consume/` (name `quick_consume`) — see §5.1.3; redirects back to stock detail with a Django message |
| List entry | "Consumption" link |
| Detail | `operation_detail_view` — shows the operation total + settlement status + auto movement lines + reversal action; the individual issuance/payment transactions are hidden (one-shot — two identical amounts would confuse users) |
| Stock history | the consumed product's OUT movement appears on the Stock History page (`stock_history`); the `live` tab excludes CONSUMED products (`stock_detail`) |
| Reverse | `operation_reverse_view` — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source=project · VC2 dest=system · VC3 source active · VC4 dest active · VC5 source fund active · VC6 target fund active · VC7 amount>0 · VC8 officer staff · VC9 officer active · VC10 not closed-period · VC11 covering period exists · VC12 balance exempt · VC13 tx entity-type · VC14 tx op-type · VC15 source≠target · VC16 consumable FEED/MEDICINE (`can_be_consumed`) · VC17 product linked · VC18 ownership · VC19 availability ≤ on-hand · VC20 unit multiple · VC21 product not terminal

**create — effects:** SC1 issuance tx · SC2 non-cash payment tx · SC3 amounts equal · SC4 direction project→system · SC5 settled immediately · SC6 no cash flow · SC7 auto outbound lines · SC8 status ACTIVE while partial on-hand remains, CONSUMED at zero on-hand · SC9 COGS (P&L ▼, inventory ▼ once) · SC10 period assigned

**quick-consume — guards:** QC1 officer staff · QC2 ownership · QC3 consumable nature + flag · QC4 quantity > 0 · QC5 availability ≤ on-hand · QC6 unit multiple · QC7 date parseable · QC8 system entity present

**quick-consume — effects:** QCS1 delegates to `ConsumptionOperation.create(...)` → SC1–SC10 full pipeline in one POST

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no explicit txs · VR4 reversal dependency guard · VR5 no adjustments (n/a) · VR6 reason required (view)

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 identity copied · SR4 issuance counter-tx · SR5 payment counter-tx · SR6 type/amount preserved · SR7 auto lines reversed · SR8 ledger negated · SR9 status restored to ACTIVE · SR10 reversal owns no txs · SR11 COGS negated (P&L restored) · SR12 fund balance unchanged · SR13 differential invariant

**pay / immutability:** BP1 `process_payment` no-op · BP2 `create_payment_transaction` blocked after create · IM1/IM2/IM3 source/destination/amount immutable

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| Auto movement line | | SC7, VC17 |
| Ledger / stock state | | SC9 |
| Status: ACTIVE while partial → CONSUMED at zero | | SC8 |
| Status reuse blocked | | VC21 |
| Tx creation + counts | | SC1, SC2, SC4 |
| Settlement | | SC3, SC5 |
| COGS / P&L | | SC9 |
| Non-cash balance | | SC6 |
| Reverse happy path | | SR1 |
| Auto lines reversed | | SR7, SR8 |
| Ledger negation | | SR8 |
| Counter txs | | SR4–SR6, VR3 |
| Status restored ACTIVE | | SR9 |
| COGS negated (P&L restored) | | SR11 |
| Non-cash balance on reverse | | SR12 |
| Stock history shows OUT | | SC7, SC8 (UI) |
| Live tab excludes consumed | | SC8 (UI) |
| Quick-consume full pipeline | | QCS1, SC1–SC10 |
| Quick-consume form renders | | QC (UI) |
| Quick-consume partial | | QCS1 (partial) |
| Quick-consume availability | | QC5, VC19 |
| Quick-consume officer | | QC1, VC8 |
| Quick-consume nature | | QC3, VC16 |
| Quick-consume ownership | | QC2, VC18 |

---

## 11. Tasks

- [x] Verify `CONSUMPTION_ISSUANCE` + `CONSUMPTION_PAYMENT` created on save (non-cash payment)
- [x] Verify transaction fund direction: `project.fund → system.fund` for both
- [x] Verify operation is fully settled immediately
- [x] Verify `CONSUMPTION_PAYMENT` is excluded from `payment_types()` → no balance / payable / receivable effect
- [x] Verify `CONSUMPTION_ISSUANCE` is counted as **COGS** in `Entity.profit_loss()` (P&L reduced once; `end_assets` reduced once via inventory)
- [x] Verify all validation branches VC1–VC21 (VC16–VC21 consumable/ownership/availability/unit/status rules)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `create_payment_transaction()` is blocked after creation (one-shot)
- [x] Verify auto outbound movement lines; product status ACTIVE while partial on-hand remains and CONSUMED once fully written off (net presence 0)
- [x] Verify reversal creates counter-transactions `system.fund → project.fund` and reverses auto lines
- [x] Verify product status restored to ACTIVE on reversal (reversal-aware `Product.status`)
- [x] Verify COGS is negated on reversal (P&L restored) and fund balance stays unchanged
- [x] Verify the one-step `quick_consume` view reuses `ConsumptionOperation.create(...)` and enforces officer/ownership/nature/availability/unit guards
- [x] UI: stock detail `live` tab renders the quick-consume form; Stock History shows the OUT movement; CONSUMED products leave `live`
- [x] Complete test suite covering all branches; each test has a small number of assertions (one behavior per test)
- [ ] Add a consumption-focused test pinning VR4 (reversal dependency guard: consumed product moved again in a later non-reversed outbound op)
- [ ] Pin the shared-engine branches (VC1–VC15, VC18–VC20, VR1–VR3, VR5, VR6) with consumption-specific focused tests where missing
- [ ] Register remaining operation specs under the same contract structure (see [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md))
