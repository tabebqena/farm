# Capital Gain — Operation Contract

**Epic:** 10.2 — Miscellaneous One-Shot Operations
**Type:** One-shot, auto-settled
**Actions:** `create`, `reverse`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Capital Gain** operation.
> Every clause below is registered to its implementing code (model → mixin → transaction → view) and to its pinning test.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> Other operations follow the same structure — see [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md).
>
> **Purpose.** Capital Gain records a **value write-up** of an asset already owned by the project (e.g. a calf's re-valuation to its current market price). It is a **non-cash, inventory-value-only** operation: it never moves real money and never changes the project's fund balance.

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.CAPITAL_GAIN` (`"CAPITAL_GAIN"`) | |
| Proxy class | `CapitalGainOperation` | |
| URL slug | `"capital-gain"` | |
| Label | `"Capital Gain Issuance"` | |
| Theme | `danger` / `bi-box-arrow-up-right` (defaults) | |
| Source role | `system` | |
| Destination role | `url` (must be a Project) | |
| Registered in | `PROXY_MAP` | |
| Cross-op reference | row CG | [`operations-comparison.md`](operations-comparison.md) |

**Configuration flags**:

| Flag | Value | Meaning |
|------|-------|---------|
| `_issuance_transaction_type` | `CAPITAL_GAIN_ISSUANCE` | issuance tx created on save |
| `_payment_transaction_type` | `CAPITAL_GAIN_PAYMENT` | payment tx created on save (one-shot) |
| `_is_one_shot_operation` | `True` | payment fires at create; no standalone pay action |
| `can_pay` | `False` | `process_payment()` is a no-op |
| `is_partially_payable` | `False` | payment must equal amount (one-shot) |
| `max_payment_transaction_count` | `1` | exactly one payment tx ever |
| `check_balance_on_payment` | `False` | no fund-balance gate — the System payer is exempt |
| `has_category` / `category_required` | `False` | no financial category |
| `has_repayment` | `False` | no repayment action |
| `has_invoice` | `True` | links the gain to an existing owned product via an invoice item |
| `creates_assets` / `can_create_movement` | `False` | value-only — **no** `InventoryMovementLine` is created |
| `is_adjustable` / `is_items_adjustable` | `False` | not adjustable |

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row links the clause to the code that must honor it.

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_source`/`clean_destination` + `payment_source_fund`/`payment_target_fund` | |
| Proxy registry / URL→class resolution | |
| Shared `Operation` engine (`clean`, `save`, `reverse`, `create`, `resolve_request`, period assignment, reversable tx types, inventory-owner helpers) | |
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
| One-shot / single-payment guard | `LinkedPaymentTransactionMixin.create_payment_transaction()` |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | `ReversableModel` + `Operation.reverse()` |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | |
| `CAPITAL_GAIN_ISSUANCE` (system → project, issuance) | |
| `CAPITAL_GAIN_PAYMENT` (system → project, **non-cash**) | **excluded** from |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Project balance = incoming payment txs − outgoing payment txs (payment-types only) | `Entity.balance_at` |
| System (virtual) never balance-checked | `Entity.can_pay` |
| Open financial period auto-created on entity creation | `Entity.save()` |
| P&L income — `CAPITAL_GAIN_ISSUANCE` (target = fund) | `Entity.profit_loss()` |
| Movement-based inventory value includes `capital_delta` (gain/loss) | `capital_delta()` + `movement_state()` |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Dedicated create view (Product Evaluation) | `EvaluationCreateView` |
| Evaluation form (product picker, new unit price, ownership-restricted queryset) | `EvaluationForm` |
| Valuation-delta computation → picks `CapitalGainOperation` / `CapitalLossOperation` | `EvaluationCreateView.post()` |
| Generic create view (secondary path, list links commented out) | `OperationCreateView` |
| POST parsing/validation | `OperationDataValidator` |
| Reverse view (reason required) | `operation_reverse_view` |
| Detail view (aggregate amount + reversal action; per-transaction list hidden — one-shot) | `operation_detail_view` |
| URL: `/<pk>/evaluate/<product_pk>/` | |
| URL: `/<pk>/<op_type>/create` (secondary) | |
| URL: `/<pk>/reverse/` | |
| URL: `/<pk>/detail/` | |
| Templates | ; entry button; operation-list links commented out |

### 2.6 Tests

| Concern | Test file |
|---------|-----------|
| Create branches | |
| Reverse branches | |
| Inventory valuation / status | |
| Period valuation (single count) | |
| Evaluation ownership guard | |
| Coverage manifest (executable branch registry) | |

---

## 3. Money flow & entities

- **Source (payer):** the single **System** entity (`is_system=True`). Virtual — never balance-checked, exempt from payment balance checks.
- **Destination (receiver):** the **Project** entity in the URL (`is_project=True`, `_dest_role="url"`). Its fund is the target fund; the project must be `active=True`.
- **Transaction flow** (both on create, system → project):

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `CAPITAL_GAIN_ISSUANCE` | `system.fund → project.fund` | none (issuance, not a payment type) |
| 2 | `CAPITAL_GAIN_PAYMENT` | `system.fund → project.fund` | **none** — non-cash bookkeeping: `CAPITAL_GAIN_PAYMENT` is **excluded** from `payment_types()`, so the project's fund balance never changes |

- **Payment source fund:** `self.source` (system)
- **Payment target fund:** `self.destination` (project)
> **No cash flow.** The gain is carried entirely by inventory valuation — `capital_delta()` adds `quantity × unit_price` for each **active** (non-reversed) `CAPITAL_GAIN` invoice item on the linked product.

---

## 4. Settlement model

Derived from `LinkedPaymentTransactionMixin` using payment-type transactions only:

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

Entry points: model `CapitalGainOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx, then payment tx). Through the UI, the entry point is `EvaluationCreateView.post()`, which computes the valuation delta and calls `Operation.create()` on the proxy.

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source is System | `source.is_system` | `ValidationError` | `"Capital Gain source must be the System entity."` | `clean_source` | |
| VC2 | Destination is Project | `destination.is_project` | `ValidationError` | `"Capital Gain destination must be a Project entity."` | `clean_destination` | |
| VC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | `Operation.clean()` | structural (System is always active) |
| VC4 | Destination entity active | `destination.active` | `ValidationError` | same as VC3 | `Operation.clean()` | |
| VC5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | `SourceFundMixin` | structural (System is always active) |
| VC6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | `TargetFundMixin` | merged with VC4 |
| VC7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | |
| VC8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | `OfficerMixin` | |
| VC9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | `OfficerMixin` | |
| VC10 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | `Operation.clean()` | covered by period suite |
| VC11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | `Operation.save()` | covered by period suite |
| VC12 | Balance exempt (system payer) | no balance check | never fails | — | `check_balance_on_payment=False` | |
| VC13 | Tx entity-type contract | `source.is_system` and `target.is_project` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | `Transaction.create()` | implied by VC1/VC2 (model clean blocks first) |
| VC14 | Tx operation-type allowed | document is `CAPITAL_GAIN` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | `Transaction.create()` | implied by VC1/VC2 |
| VC15 | Source ≠ target | system ≠ project | always true | `"Source and target funds must be different."` | `Transaction.clean()` | structural (system ≠ project) |
| VC16 | Product ownership (UI) | product belongs to the evaluated project | `ValidationError` / form rejects | `"Product '…' does not belong to '…' and cannot be evaluated."` | `EvaluationForm` + `EvaluationCreateView.post()` + `Operation.save_inventory()` | |
| VC17 | Product status eligible | product not SOLD/DEAD/CONSUMED/REMOVED | `ValidationError` | `"Product '…' has status … and cannot be used in new operations."` | `Product.validate_active()` + `Operation.save_inventory()` | |
| VC18 | Product template compatible | template `accepts_operation("CAPITAL_GAIN")` | `ValidationError` | nature↔operation incompatibility | `ProductTemplate.accepts_operation()` | structural (allowed for all natures) |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | 1 × `CAPITAL_GAIN_ISSUANCE`, amount `== op.amount`, `system → project` | `LinkedIssuanceTransactionMixin.save()` | |
| SC2 | Payment tx created | 1 × `CAPITAL_GAIN_PAYMENT`, amount `== op.amount`, `system → project` | `LinkedPaymentTransactionMixin.save()` | same as SC1 |
| SC3 | Tx amounts equal op amount | both txs `amount == op.amount` | transaction creation | |
| SC4 | Tx fund direction | both txs `source=system`, `target=project` | | |
| SC5 | Fully settled immediately | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | `LinkedPaymentTransactionMixin` | |
| SC6 | No cash flow — project fund unchanged | `project.balance` unchanged by the gain | `CAPITAL_GAIN_PAYMENT ∉ payment_types()` → `Entity.balance_at` | |
| SC7 | Inventory value ▲ | `Product.current_value`/`inventory_value` increases by the gain (`capital_delta`) | `capital_delta()` + `Product.current_value` | |
| SC8 | P&L income ▲ | `profit_loss()` counts `CAPITAL_GAIN_ISSUANCE` (target=fund) as income | `Entity.profit_loss()` | covered by SC7 period test (same tx drives P&L) |
| SC9 | Value-only ledger | gain is value-only: **no** `InventoryMovementLine` created, quantity untouched | `creates_assets=False`, `can_create_movement=False` + `save_inventory` | |
| SC10 | Product status unchanged | linked product stays `ACTIVE` (not SOLD/DEAD) | `save_inventory` links item only | |
| SC11 | No double count | `end_assets` increase `==` recognized gain (counted once in inventory, once in P&L; never in cash balance) | `period.end_assets` | |
| SC12 | Period auto-assigned | `period` = the project's covering period (open period auto-created at entity creation) | `Operation.save()` + `Entity.save()` | covered by period suite |

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | `ReversableModel._validate_can_be_reversed` + view guard | |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | `ReversableModel._validate_can_be_reversed` + view guard | |
| VR3 | No explicit txs to reverse | all txs are implicit (one-shot issuance + payment) | `ValidationError` (would require manual reversal) | `"You can't reverse this object as it has non-reversed transactions…"` | `ReversableModel._requires_transaction_reversal` + `Operation._implicit_reversable_transaction_types` | implied by successful reverse |
| VR4 | No non-reversed adjustments | n/a — Capital Gain is not adjustable | never fails | — | `is_adjustable=False` | n/a |
| VR5 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | `operation_reverse_view` | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | `ReversableModel.reverse()` | |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | `ReversableModel.reverse()` | |
| SR3 | Reversal inherits identity | `amount`, `source`, `destination` copied; `is_reversal=True`, `is_reversed=False` | `ReversableModel._get_reverse_kwargs` | |
| SR4 | Counter-tx for issuance | `project → system`, same amount, same type, `reversal_of=original` | `Transaction.reverse()` | |
| SR5 | Counter-tx for payment | `project → system`, same amount, same type, `reversal_of=original` | same as SR4 | |
| SR6 | Counter-txs preserve type + amount | `counter.type == original.type`, `counter.amount == original.amount` | same as SR4 | |
| SR7 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | `LinkedIssuanceTransactionMixin.save()` | covered by reversal suite (implicit) |
| SR8 | Project fund unchanged after reversal | `project.balance` unchanged (gain is non-cash) | `balance_at` | |
| SR9 | Settlement state cleared | `amount_settled == 0`, `is_fully_settled == False` | `amount_settled` | covered by reversal suite (implicit) |
| SR10 | Reason flows to reversal | `reversal.description` contains the reason | `ReversableModel.reverse()` | covered by shared engine |
| SR11 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger) | whole engine | |
| SR12 | Product status stays ACTIVE through reversal | value write-up is not a status transition; reversal does not mutate the product | `save_inventory` / reversal path | |

### 5.3 `pay` (one-shot guard)

There is **no standalone pay action** for Capital Gain:

| Branch | Behavior | Enforced by | Pinned by test |
|--------|----------|-------------|----------------|
| `process_payment()` called | no-op (returns immediately — `can_pay=False`) | `process_payment` | n/a (covered by `can_pay=False`) |
| `create_payment_transaction()` called after create | `ValidationError` — one-shot allows a single payment only, amount must equal `op.amount` | `create_payment_transaction` | |

### 5.4 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by `ImmutableMixin` via `_immutable_fields`.

| Branch | Enforced by | Pinned by test |
|--------|-------------|----------------|
| `source` changed after save | `ImmutableMixin.save()` | |
| `destination` changed after save | `ImmutableMixin.save()` | |
| `amount` changed after save | `ImmutableMixin.save()` | |

---

## 6. Period & financial-period contract

- Every real (non-system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — `Entity.save()`.
- The operation's governing entity (`period_entity`) is the **destination project** (`_dest_role = "url"`) — `Operation.period_entity`.
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC11).
- New operations dated inside a **closed** period are rejected (VC10).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period (`_reverse_period`).

---

## 7. Entity roles & balance contract

- Project is the only allowed destination; System the only allowed source — enforced at model (VC1/VC2) and transaction (VC13) layers.
- `project.balance` is derived exclusively from **payment-type** transactions (`balance_at`); `CAPITAL_GAIN_PAYMENT` is **not** a payment type, so the gain never inflates the project's fund balance.
- System is **virtual**: `can_pay` always returns `True`, so gains are never blocked by fund balance (VC12).
- Inventory value carries the gain via `capital_delta()` (only **non-reversed** capital ops count), so the gain appears exactly once in movement-based valuation — never in the cash balance (SC11).

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Primary create route | `GET/POST /<project_pk>/evaluate/<product_pk>/` → `EvaluationCreateView`; also `/<pk>/evaluate/` without a product |
| Entry point | **"Record Evaluation"** button on the product's stock detail page, restricted to `ACTIVE` products |
| Form | `EvaluationForm` — product picker (ownership-restricted to the project's products), `new_unit_price` (`min 0.01`), date, notes |
| Direction selection | computed from `delta = (new_unit_price − current_unit_price) × quantity`: `delta > 0 → CapitalGainOperation`, `delta < 0 → CapitalLossOperation`, ` | delta | < 0.01 → no operation` (`post()`) |
| Source selection | locked to the single **System** entity (`_source_role="system"`, resolved by `resolve_request`); no picker |
| Destination selection | the **Project** from the URL (`_dest_role="url"`); no secondary-entity field |
| Amount | derived from the invoice item (`quantity × | Δ unit price | `) created by the evaluation view |
| Category | hidden (no category) |
| Secondary create route | `/<pk>/<op_type>/create` with `op_type="capital-gain"` exists (`OperationCreateView`), but the operation-list links are **commented out** |
| Detail | `operation_detail_view` — shows the operation total + settlement status + reversal action; the individual issuance/payment transactions are hidden (one-shot — two identical amounts would confuse users) |
| Reverse | `operation_reverse_view` — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source=system · VC2 dest=project · VC3 source active · VC4 dest active · VC5 source fund active · VC6 target fund active · VC7 amount>0 · VC8 officer staff · VC9 officer active · VC10 not closed-period · VC11 covering period exists · VC12 balance exempt · VC13 tx entity-type · VC14 tx op-type · VC15 source≠target · VC16 product ownership · VC17 product status eligible · VC18 template compatible

**create — effects:** SC1 issuance tx · SC2 payment tx · SC3 amounts equal · SC4 direction system→project · SC5 settled immediately · SC6 no cash flow (fund unchanged) · SC7 inventory value ▲ · SC8 P&L income ▲ · SC9 value-only (no movement line) · SC10 product ACTIVE · SC11 no double count · SC12 period assigned

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no explicit txs · VR4 no adjustments (n/a) · VR5 reason required (view)

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 identity copied · SR4 issuance counter-tx · SR5 payment counter-tx · SR6 type/amount preserved · SR7 reversal owns no txs · SR8 fund unchanged after reversal · SR9 settlement cleared · SR10 reason in description · SR11 differential invariant · SR12 product stays ACTIVE

**pay / immutability:** BP1 `process_payment` no-op · BP2 `create_payment_transaction` blocked after create · IM1/IM2/IM3 source/destination/amount immutable

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| Tx creation + counts | | SC1, SC2 |
| Tx amounts | | SC3 |
| Tx direction | | SC4 |
| Settlement | | SC5 |
| Non-cash (fund unchanged) | | SC6 |
| Source validation | | VC1 |
| Destination validation | | VC2, VC4 |
| Amount | | VC7 |
| Officer | | VC8, VC9 |
| Immutability | | IM1–IM3 |
| One-shot guard | | BP2 |
| Balance exempt | | VC12 |
| Reverse happy path | | SR1–SR3 |
| Counter txs | | SR4–SR6 |
| Non-cash after reversal | | SR8 |
| Reverse constraints | | VR1, VR2 |
| Differential invariant | | SR11 |
| Value-only, product ACTIVE (create + reverse) | | SC9, SC10, SR12 |
| Inventory valuation (capital_delta) | | SC7 |
| Product status ACTIVE | | SC10 |
| Single-count valuation | | SC7, SC11 |
| Evaluation ownership guard | | VC16, VC17 |

---
