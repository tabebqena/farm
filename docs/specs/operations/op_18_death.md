# Death — Operation Contract

**Epic:** Inventory / Livestock — One-Shot
**Type:** One-shot, auto-settled, removes assets (`has_invoice=True`)
**Actions:** `create`, `move items` (auto), `reverse`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Death** operation.
> Every clause below is registered to its implementing code (model → mixin → transaction → view) and to its pinning test.
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
| `_issuance_transaction_type` | `DEATH_ISSUANCE` | issuance tx created on save |
| `_payment_transaction_type` | `DEATH_PAYMENT` | payment tx created on save (one-shot) — **non-cash bookkeeping** |
| `_is_one_shot_operation` | `True` | payment fires at create; no standalone pay action |
| `can_pay` | `False` | `process_payment()` is a no-op |
| `is_partially_payable` | `False` | payment must equal amount (one-shot) |
| `max_payment_transaction_count` | `1` | exactly one payment tx ever |
| `check_balance_on_payment` | `False` | write-off — no fund-balance check at create |
| `has_category` / `category_required` | `False` | no financial category |
| `has_repayment` | `False` | no repayment action |
| `has_invoice` | `True` | invoice items (selected existing products) + auto inventory movements |
| `creates_assets` | `False` (default) | links to **existing** assets; no lazy product creation |

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row links the clause to the code that must honor it.

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
| Source fund exists + active | `SourceFundMixin` |
| Target fund exists + active | `TargetFundMixin` |
| Issuance tx creation on save | `LinkedIssuanceTransactionMixin` |
| One-shot payment tx creation + settlement (`amount_settled`, `is_fully_settled`) | `LinkedPaymentTransactionMixin` |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | `ReversableModel` + `Operation.reverse()` |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | |
| `DEATH_ISSUANCE` (project → system, no balance) | |
| `DEATH_PAYMENT` (project → system, **non-cash — excluded from `payment_types()`**) | |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Balance derivation (payment types only — `DEATH_PAYMENT` excluded, so a death never drains a fund balance) | `Entity.balance_at` |
| Virtual/system-entity payment exemption | `Entity.can_pay` |
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

- **Source (payer):** the **Project** entity in the URL (`is_project=True`). Its fund is the source fund; the project owns the dead asset.
- **Destination (receiver):** the single **System** entity (`is_system=True`). Virtual — never balance-checked, exempt from fund-balance validation (`payment_target_fund`).
- **Transaction flow** (both on create, project → system):

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `DEATH_ISSUANCE` | `project.fund → system.fund` | none (issuance, not a payment type) |
| 2 | `DEATH_PAYMENT` | `project.fund → system.fund` | **none** — non-cash bookkeeping, **excluded from `payment_types()`** |

- **Payment source fund:** `self.source` (project)
- **Payment target fund:** `self.destination` (system)
> **No cash flow.** A death reduces the project's `end_assets` **exactly once**, via movement-based inventory value (the dead animal's carried cost, `inventory_value()`). `DEATH_PAYMENT` is non-cash — it never drains the project's fund balance (not in `payment_types()`, so no balance/payable/receivable effect).

---

## 4. Settlement model

Derived from `LinkedPaymentTransactionMixin` using payment-type transactions only (note: `DEATH_PAYMENT` is **not** a payment type for balance purposes, but it *is* the one-shot settlement transaction for this operation):

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

Entry points: model `DeathOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx, then payment tx), then the invoice formset → `save_inventory()` → `_auto_create_inventory_movements()`.

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source is Project | `source.is_project` | `ValidationError` | `"Death source must be a Project entity."` | `clean_source` | |
| VC2 | Destination is System | `destination.is_system` | `ValidationError` | `"Death destination must be the System entity."` | `clean_destination` | |
| VC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | `Operation.clean()` | |
| VC4 | Destination entity active | `destination.active` | `ValidationError` | same as VC3 | `Operation.clean()` | shared engine suite |
| VC5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | `SourceFundMixin` | shared engine suite |
| VC6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | `TargetFundMixin` | shared engine suite |
| VC7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | |
| VC8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | `OfficerMixin` | |
| VC9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | `OfficerMixin` | shared engine suite |
| VC10 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | `Operation.clean()` | period suite |
| VC11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | `Operation.save()` | period suite |
| VC12 | Balance exempt (write-off) | no balance check | never fails | — | `check_balance_on_payment=False` | structural (`can_pay`-less one-shot) |
| VC13 | Tx entity-type contract | `source.is_project` and `target.is_system` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | `Transaction.create()` | implied by VC1/VC2 (model clean blocks first) |
| VC14 | Tx operation-type allowed | document is `DEATH` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | `Transaction.create()` | implied by VC1/VC2 |
| VC15 | Source ≠ target | project ≠ system | always true | `"Source and target funds must be different."` | `Transaction.clean()` | structural (project ≠ system) |
| VC16 | Template is die-able ANIMAL | `nature == ANIMAL` **and** `can_die=True` | `ValidationError` | template rejected by `accepts_operation(DEATH)` | `ProductTemplate.accepts_operation` | |
| VC17 | Product linked (must be an existing asset) | `selected_product` present on the invoice item | form/`ValidationError` | missing-product error | `InvoiceItemSelectFormSet` + `save_inventory` | implied by create flow |
| VC18 | Ownership — product belongs to source project | `selected.entity == inventory_owner_entity` | `ValidationError` | `"Product '%(p)s' does not belong to '%(entity)s' and cannot be used in this operation."` | `save_inventory` | shared inventory suite |
| VC19 | Availability — quantity ≤ on-hand | `quantity ≤ movement_state(product).quantity` | `ValidationError` | availability error | `InventoryMovementLine.clean` + `_auto_create_inventory_movements` | shared inventory suite |
| VC20 | Unit consistency | quantity is a multiple of `product_template.minimum_quantity` | `ValidationError` | unit-step error | inventory form / movement clean | shared inventory suite |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | 1 × `DEATH_ISSUANCE`, amount `== op.amount`, `project → system` | `LinkedIssuanceTransactionMixin.save()` | |
| SC2 | Payment tx created (non-cash) | 1 × `DEATH_PAYMENT`, amount `== op.amount`, `project → system`; **not** a `payment_types()` type → no balance/payable/receivable effect | `LinkedPaymentTransactionMixin.save()` | |
| SC3 | Tx amounts equal op amount | both txs `amount == op.amount` | transaction creation | |
| SC4 | Tx fund direction | both txs `source=project`, `target=system` | | |
| SC5 | Fully settled immediately | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | `LinkedPaymentTransactionMixin` | |
| SC6 | No cash flow | project fund balance unchanged (payment non-cash); system (virtual) ▲ in bookkeeping only | `payment_types()` exclusion + `Entity.balance_at` | differential invariant |
| SC7 | Auto outbound movement lines | one movement line per item at item qty, valued at the product's carried cost | `_auto_create_inventory_movements` | (setup) |
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
| VR4 | Reversal dependency guard | none of the dead products were moved again in a later non-reversed outbound op | `ValidationError` | `"Cannot reverse this operation: its products were moved again in a later operation."` | `Operation.reverse()` | shared outbound-op suite (SALE/CONSUMPTION) — **birth/death-focused test pending** |
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
| Die-able product | selectable products are those whose template is ANIMAL **and** `can_die=True` (`accepts_operation(DEATH)`); the picker filters to the project's active on-hand stock |
| POST parsing | `OperationDataValidator` — date format, description, category (n/a), `amount_paid` (n/a, forced 0) |
| List entry | "Death" link |
| Detail | `operation_detail_view` — shows the operation total + settlement status + auto movement lines + reversal action; the individual issuance/payment transactions are hidden (one-shot — two identical amounts would confuse users) |
| Reverse | `operation_reverse_view` — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source=project · VC2 dest=system · VC3 source active · VC4 dest active · VC5 source fund active · VC6 target fund active · VC7 amount>0 · VC8 officer staff · VC9 officer active · VC10 not closed-period · VC11 covering period exists · VC12 balance exempt · VC13 tx entity-type · VC14 tx op-type · VC15 source≠target · VC16 die-able ANIMAL (`can_die`) · VC17 product linked · VC18 ownership · VC19 availability ≤ on-hand · VC20 unit multiple

**create — effects:** SC1 issuance tx · SC2 non-cash payment tx · SC3 amounts equal · SC4 direction project→system · SC5 settled immediately · SC6 no cash flow · SC7 auto outbound lines · SC8 status DEAD · SC9 inventory value ▼ once · SC10 period assigned

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no explicit txs · VR4 reversal dependency guard · VR5 no adjustments (n/a) · VR6 reason required (view)

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 identity copied · SR4 issuance counter-tx · SR5 payment counter-tx · SR6 type/amount preserved · SR7 auto lines reversed · SR8 ledger negated · SR9 status restored to ACTIVE · SR10 reversal owns no txs · SR11 differential invariant

**pay / immutability:** BP1 `process_payment` no-op · BP2 `create_payment_transaction` blocked after create · IM1/IM2/IM3 source/destination/amount immutable

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

