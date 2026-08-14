# Death — Operation Contract

**Epic:** Inventory / Livestock — One-Shot (stock event)
**Type:** Stock event (no accounting transactions), removes assets (`has_invoice=True`)
**Actions:** `create`, `move items` (auto), `reverse`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Death** operation.
> Every clause below names its implementing code (model → mixin → transaction → view) and its pinning test — as plain names, never links, so renames do not break the spec.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> See [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md) for the shared structure and
> [`op_1_cash_injection.md`](op_1_cash_injection.md) for a fully worked example.

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.DEATH` (`"DEATH"`) | |
| Proxy class | `DeathOperation` | |
| URL slug | `"death"` | |
| Label | `"Death"` | |
| Theme | `danger` / `bi-box-arrow-up-right` (inherited default) | |
| Source role | `url` (must be a Project) | |
| Destination role | `system` | |
| Registered in | `PROXY_MAP` | |
| Cross-op reference | row DE | [`operations-comparison.md`](operations-comparison.md) |

**Configuration flags**:

| Flag | Value | Meaning |
|------|-------|---------|
| `can_pay` | `False` | no payment action |
| `is_partially_payable` | `False` | n/a (no settlement) |
| `check_balance_on_payment` | `False` | n/a (no payment) |
| `has_category` / `category_required` | `False` | no financial category |
| `has_repayment` | `False` | no repayment action |
| `has_invoice` | `True` | invoice items (selected existing products) + auto inventory movements |
| `creates_assets` | `False` (default) | links to **existing** assets; no lazy product creation |

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row names the code that must honor it (plain names, no links).

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_source`/`clean_destination` + payment funds | |
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
| **None** — Death creates no `Transaction` rows | (no transaction mixins inherited) |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Fund balance never affected (no payment) | `Entity.balance_at` (no Death tx types are payment types) |
| Open financial period auto-created on entity creation | `Entity.save()` |

### 2.5 Inventory layer (death-specific)

| Concern | Implementing code |
|---------|-------------------|
| Die-able template gating: ANIMAL nature **and** `can_die=True` | (`accepts_operation`), `can_die` field |
| Product selection (existing asset, not created) — `InvoiceItemSelectFormSet` | |
| Ownership guard: selected product belongs to the source project | `save_inventory` |
| Availability guard: quantity ≤ physically-present on-hand (movement-ledger) | `_auto_create_inventory_movements` + `InventoryMovementLine.clean` |
| Auto outbound movement lines; product status DEAD; restored to ACTIVE on reversal | `Product.status` |
| Movement-based valuation (`movement_state`, `inventory_value`) — dead value leaves inventory **once** | `inventory_value`, `_OUTBOUND_TYPES` |
| Reversal dependency guard (products moved again later) | `Operation.reverse()` |

### 2.6 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (dedicated Death) | `DeathCreateView` |
| POST parsing/validation | `OperationDataValidator` |
| Reverse view (reason required) | `operation_reverse_view` |
| Detail view (aggregate amount + movement lines + reversal action; per-transaction list hidden — one-shot) | `operation_detail_view` |
| URL: `/<pk>/death/create` | |
| URL: `/<pk>/reverse/` | |
| URL: `/<pk>/detail/` | |
| Templates | |

### 2.7 Tests

| Concern | Test file |
|---------|-----------|
| Create branches (config, validation, issuance + payment, settlement) | |
| Reverse branches (reversal record, counter-tx, auto lines reversed, ledger negation, status DEAD→ACTIVE) | |
| `can_die` gating + animal-template rules | |
| Coverage manifest (executable branch registry) | |

---

## 3. Money flow & entities

- **Source (role):** the **Project** entity in the URL (`is_project=True`). It owns the dead asset.
- **Destination (role):** the single **System** entity (`is_system=True`). Virtual.
- **No transactions are created.** A death reduces the project's `end_assets` **exactly once**, via movement-based inventory value (the dead animal's carried cost, `inventory_value()`). The project's fund balance, payables and receivables are never affected.

---

## 4. Settlement model

There is **no settlement model** — Death does not inherit the payment/settlement machinery.
`amount_settled`, `is_fully_settled`, `amount_remaining_to_settle`, `payment_transactions` do
**not** exist on a `DeathOperation`. The operation's value lives in inventory.

---

## 5. Actions

### 5.1 `create`

Entry points: model `DeathOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()`, then the invoice formset → `save_inventory()` → `_auto_create_inventory_movements()`.

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source is Project | `source.is_project` | `ValidationError` | `"Death source must be a Project entity."` | `clean_source` | |
| VC2 | Destination is System | `destination.is_system` | `ValidationError` | `"Death destination must be the System entity."` | `clean_destination` | |
| VC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | `Operation.clean()` | |
| VC4 | Destination entity active | `destination.active` | `ValidationError` | same as VC3 | `Operation.clean()` | shared engine suite |
| VC5 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | |
| VC6 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | `OfficerMixin` | |
| VC7 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | `OfficerMixin` | shared engine suite |
| VC8 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | `Operation.clean()` | period suite |
| VC9 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | `Operation.save()` | period suite |
| VC10 | Template is die-able ANIMAL | `nature == ANIMAL` **and** `can_die=True` | `ValidationError` | template rejected by `accepts_operation(DEATH)` | `ProductTemplate.accepts_operation` | |
| VC11 | Product linked (must be an existing asset) | `selected_product` present on the invoice item | form/`ValidationError` | missing-product error | `InvoiceItemSelectFormSet` + `save_inventory` | implied by create flow |
| VC18 | Ownership — product belongs to source project | `selected.entity == inventory_owner_entity` | `ValidationError` | `"Product '%(p)s' does not belong to '%(entity)s' and cannot be used in this operation."` | `save_inventory` | shared inventory suite |
| VC19 | Availability — quantity ≤ on-hand | `quantity ≤ movement_state(product).quantity` | `ValidationError` | availability error | `InventoryMovementLine.clean` + `_auto_create_inventory_movements` | shared inventory suite |
| VC20 | Unit consistency | quantity is a multiple of `product_template.minimum_quantity` | `ValidationError` | unit-step error | inventory form / movement clean | shared inventory suite |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | No transactions created | `get_all_transactions().count() == 0` (no issuance, no payment) | (no transaction mixins) | |
| SC2 | No settlement machinery | `amount_settled`/`is_fully_settled`/`create_payment_transaction` absent | (no payment mixin) | |
| SC3 | Auto outbound movement lines | one movement line per item at item qty, valued at the product's carried cost | `_auto_create_inventory_movements` | (setup) |
| SC4 | Status DEAD | the written-off product `status == DEAD` | `Product.status` | |
| SC5 | Inventory value drops once | `inventory_value()` decreases by the carried cost | `movement_state` + `inventory_value` | |
| SC6 | Period auto-assigned | `period` = the project's covering period | `Operation.save()` | covered by period suite |
| SC7 | Fund balance unchanged | `balance_at()` unaffected (no payment) | `Entity.balance_at` | |
| SC8 | Product status DEAD | the written-off product's movement-based `status == DEAD` | `Product.status` | |
| SC9 | Inventory value decreased once | `movement_state(product)` → net outbound; `inventory_value()` drops by the dead value; `end_assets` ▼ once (via inventory, not cash) | `movement_state` + `inventory_value` | (baseline before reversal) |
| SC10 | Period auto-assigned | `period` = the project's covering period (open period auto-created at entity creation) | `Operation.save()` + `Entity.save()` | covered by period suite |

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | `ReversableModel._validate_can_be_reversed` + view guard | |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | `ReversableModel._validate_can_be_reversed` + view guard | |
| VR3 | No explicit txs to reverse | all txs are implicit (one-shot issuance + payment) | `ValidationError` (would require manual reversal) | `"You can't reverse this object as it has non-reversed transactions…"` | `ReversableModel._requires_transaction_reversal` + `Operation._implicit_reversable_transaction_types` | implied by successful reverse |
| VR4 | Reversal dependency guard | none of the dead products were moved again in a later non-reversed outbound op | `ValidationError` | `"Cannot reverse this operation: its products were moved again in a later operation."` | `Operation.reverse()` | **Defensive guard (unreachable via normal flows):** there is **no partial death** — a death always writes off the full on-hand quantity of the (INDIVIDUAL) animal, so the dead product becomes terminal (DEAD) and `Product.validate_active()` blocks any later outbound move. The shared guard code path is therefore pinned by the reachable **partial** outbound scenarios in the SALE and CONSUMPTION suites (`test_reversal_blocked_when_product_moved_again_in_later_sale` and `test_reversal_blocked_when_product_moved_again_in_later_consumption`) — the same `Operation.reverse()` clause. |
| VR5 | No non-reversed adjustments | n/a — Death is not adjustable | never fails | — | `is_adjustable=False` | n/a |
| VR6 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | `operation_reverse_view` | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | `ReversableModel.reverse()` | |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | `ReversableModel.reverse()` | |
| SR3 | Reversal inherits identity | `amount`, `source`, `destination` copied | `ReversableModel._get_reverse_kwargs` | structural (same engine as [`op_1`](op_1_cash_injection.md) SR3) |
| SR4 | Counter-tx for issuance | `system → project`, same amount, same type, `reversal_of=original` | `Transaction.reverse()` | |
| SR5 | Counter-tx for payment | `system → project`, same amount, same type, `reversal_of=original` | same as SR4 | same as SR4 |
| SR6 | Counter-txs preserve type + amount | `counter.type == original.type`, `counter.amount == original.amount` | same as SR4 | same as SR4 |
| SR7 | Auto movement lines reversed | one reversal line per original (equal qty, `reversal_of` link); originals preserved | `Operation.reverse()` → `line.reverse()` | |
| SR8 | Ledger negated | the dead product's net presence restored to its pre-death on-hand (`qty`/`value` back to baseline) | `movement_state` | |
| SR9 | Product status restored to ACTIVE | reversal-aware `Product.status` → `ACTIVE` (no resurrection of a dead stock item) | `Product.status` | |
| SR10 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | `LinkedIssuanceTransactionMixin.save()` | shared engine (cf. [`op_1`](op_1_cash_injection.md) SR7) |
| SR11 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger, inventory value) | whole engine | shared engine invariant |

### 5.3 `pay` (one-shot guard)

There is **no standalone pay action** for Death:

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
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period (`_reverse_period`).

---

## 7. Entity roles & balance contract

- Project is the only allowed source; System the only allowed destination — enforced at model (VC1/VC2) and transaction (VC13) layers.
- `DEATH_PAYMENT` is **deliberately excluded** from `payment_types()` — it is a non-cash bookkeeping record. The project's fund balance, payables and receivables are **never** affected by a death.
- The dead asset's value leaves **exactly once** from movement-based inventory value (`inventory_value()`); `FinancialPeriod.end_assets` = cash + movement-based inventory + loans + advances, so a death reduces `end_assets` exactly once, via inventory.
- System is **virtual**: `can_pay` always returns `True`, so deaths are never blocked by fund balance (VC12).

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Create route | `POST/GET /<project_pk>/death/create` → `DeathCreateView` |
| Source selection | the **Project** from the URL (`_source_role="url"`); no picker |
| Destination selection | locked to the single **System** entity (`_dest_role="system"`); no secondary-entity field |
| Category | hidden (no category) |
| Amount | computed from item totals; raw `amount` POST field validated > 0 at model |
| Invoice items | `InvoiceItemSelectFormSet` (`creates_assets=False`) — one row per affected product, picking an **existing** product (`selected_product`) owned by the project |
| Die-able product | selection is restricted to **existing** products owned by the project (`InvoiceItemSelectForm` filters `selected_product` by `entity` only). The die-able / active / on-hand pre-filter described by the older draft is **not** applied in the picker — those rules are enforced at the model layer (`InvoiceItem.clean()` → `accepts_operation`, `InventoryMovementLine.clean` → availability/status/ownership). **TODO(code):** pre-filter the picker queryset by `accepts_operation(DEATH)` (ANIMAL **and** `can_die=True`), active status, and on-hand quantity so ineligible rows are not offered. |
| POST parsing | `OperationDataValidator` — date format, description, category (n/a), `amount_paid` (n/a, forced 0) |
| List entry | Death operations appear as history rows with a detail link. **Intended:** there is **no create entry in the operations-list "New Operation" dropdown** — creation is entered only from the stock detail page's per-ANIMAL "Record Death" button (`stock_detail.html` → `death_create_view`). |
| Detail | `operation_detail_view` — shows the operation total + settlement status + auto movement lines + reversal action; the individual issuance/payment transactions are hidden (one-shot — two identical amounts would confuse users) |
| Reverse | `operation_reverse_view` — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source=project · VC2 dest=system · VC3 source active · VC4 dest active · VC5 source fund active · VC6 target fund active · VC7 amount>0 · VC8 officer staff · VC9 officer active · VC10 not closed-period · VC11 covering period exists · VC12 balance exempt · VC13 tx entity-type · VC14 tx op-type · VC15 source≠target · VC16 die-able ANIMAL (`can_die`) · VC17 product linked · VC18 ownership · VC19 availability ≤ on-hand · VC20 unit multiple

**create — effects:** SC1 no transactions · SC2 no settlement machinery · SC3 auto outbound lines · SC4 status DEAD · SC5 inventory value ▼ once · SC6 period assigned · SC7 fund balance unchanged

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no explicit txs · VR4 reversal dependency guard · VR5 no adjustments (n/a) · VR6 reason required (view)

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 identity copied · SR4 no counter-txs · SR5 auto lines reversed · SR6 ledger negated · SR7 status restored to ACTIVE · SR8 differential invariant

**immutability:** IM1/IM2/IM3 source/destination/amount immutable

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| Config flags | | flags |
| Tx creation + counts | | SC1, SC2 |
| Tx direction | | SC4 |
| Tx amounts | | SC3 |
| Settlement | | SC5 |
| Source validation | | VC1, VC3 |
| Destination validation | | VC2 |
| Amount | | VC7 |
| Officer | | VC8 |
| `can_die` gating | | VC16 |
| Reverse happy path | | SR1, SR2 |
| Counter txs | | SR4–SR6 |
| Auto lines reversed | | SR7, SR8 |
| Ledger negation | | SR8, SC9 |
| Status DEAD | | SC8 |
| Status restored ACTIVE | | SR9 |
| Reverse constraints | | VR1, VR2 |
| Reversal dependency guard | defensive — shared guard pinned via SALE/CONSUMPTION partial-outbound tests (see §5.2.1 VR4) | VR4 |

