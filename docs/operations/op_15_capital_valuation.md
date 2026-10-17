# Capital Valuation (Gain & Loss) — Operation Contract

**Epic:** 10.2/10.3 — Miscellaneous One-Shot Operations (stock event)
**Type:** Stock event (no accounting transactions), value-only
**Actions:** `create`, `reverse`
**Contract status:** v3 (merged) — Capital Valuation covers **Capital Gain** (CG) and
**Capital Loss** (CL), both **value-only stock events**: neither creates `Transaction`
rows, neither has payment/settlement machinery, and both are assigned to a financial
period (and blocked inside a closed one). A valuation raises (gain) or lowers (loss) the
linked product's movement-based inventory value without changing quantity, fund balance
or `profit_loss()`.

> **Primary source of contract.** This document is the authoritative contract for the
> **Capital Valuation** operations — **Capital Gain** (CG) and **Capital Loss** (CL) —
> both served by a **single proxy class** `CapitalValuationOperation` that dispatches its
> per-type config on the row's `operation_type` (the same pattern as `CorrectionOperation`
> for correction credit/debit).
> Every clause below names its implementing code (model → mixin → view) and its pinning
> test — as plain names, never links, so renames do not break the spec.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code,
> not the spec.
> See [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md) for the shared structure and
> [`op_1_cash_injection.md`](op_1_cash_injection.md) for a fully worked example.
> The inventory value these operations change is the movement-based
> [`stock.md`](../features/stock.md) contract (`capital_delta` → `movement_state["value"]`) —
> keep that spec in sync when this operation's valuation behavior changes.

---

## 1. Identity

| Field | Capital Gain (CG) | Capital Loss (CL) | Defined in |
|-------|-------------------|-------------------|-----------|
| Operation type | `OperationType.CAPITAL_GAIN` (`"CAPITAL_GAIN"`) | `OperationType.CAPITAL_LOSS` (`"CAPITAL_LOSS"`) | |
| Proxy class | `CapitalValuationOperation` | `CapitalValuationOperation` | |
| URL slug | `"capital-gain"` | `"capital-loss"` | |
| Label | `"Capital Gain Issuance"` | `"Capital Loss Issuance"` | |
| Source role | `system` | `url` (must be a Project) | |
| Destination role | `url` (must be a Project) | `system` | |
| Registered in | `PROXY_MAP` (both types → `CapitalValuationOperation`) | `PROXY_MAP` (both types → `CapitalValuationOperation`) | |
| Config dispatch | per-type keys in `CapitalValuationOperation._VARIANT_CONFIG`, read on `operation_type` | same | |

Both `"capital-gain"` and `"capital-loss"` URL slugs resolve to this one proxy; the
evaluation view selects the variant from the signed valuation delta.

**Configuration flags:**

| Flag | Capital Gain | Capital Loss | Meaning |
|------|--------------|--------------|---------|
| `can_pay` | `False` | `False` | no payment action |
| `is_partially_payable` | `False` | `False` | n/a (no settlement) |
| `check_balance_on_payment` | `False` | `False` | n/a (no payment) |
| `has_category` | `False` | `False` | no financial category |
| `has_repayment` | `False` | `False` | no repayment action |
| `has_invoice` | `False` | `False` | no invoice items — the valuation is recorded on a dedicated valuation row, not on an `InvoiceItem` |
| `has_capital_valuation` | `True` | `True` | a `ProductCapitalValuation` row linking the owned product to a signed amount (positive = gain, negative = loss; value-only — no movement line) |

> **No accounting mixins.** `CapitalValuationOperation` (the shared Capital Gain/Loss
> proxy) inherits only `ImmutableMixin`, `AmountCleanMixin`, `OfficerMixin`,
> `ReversableModel`, `BaseModel` (via the lean `Operation` base) plus the shared
> `StockEventMixin` (non-accounting config, with `has_invoice` overridden back to `False`
> because the valuation is value-only) and `InventoryOperationMixin` (inventory engine).
> It does **not** inherit `LinkedIssuanceTransactionMixin`, `LinkedPaymentTransactionMixin`,
> `LinkedRePaymentTransactionMixin` or `AdjustableMixin` — so no transactions, no settlement,
> no repayment, no adjustments, no P&L entry in `profit_loss()`.

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row names the code that must honor it (plain names, no links).

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Single merged proxy `CapitalValuationOperation` + `_VARIANT_CONFIG` (per-type: url_str, label, roles, verbose_name) | |
| `clean_source`/`clean_destination` (dispatch on `operation_type`) | |
| Proxy registry / URL→class + slug→operation-type resolution | |
| Shared `Operation` engine (`clean`, `save`, `reverse`, `create`, `resolve_request`, period assignment, reversable tx types) + `InventoryOperationMixin` (inventory ownership helpers, reversal guards) | |
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
| **None** — Capital Valuation creates no `Transaction` rows | (no transaction mixins inherited) |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Fund balance never affected (no payment) | `Entity.balance_at` (no Capital Gain/Loss tx types) |
| P&L not affected — value flows through inventory | `Entity.profit_loss` (Gain/Loss no longer a cost/income) |
| Open financial period auto-created on entity creation | `Entity.save()` |

### 2.5 Inventory layer (capital-specific)

| Concern | Implementing code |
|---------|-------------------|
| Ownership guard: the evaluated product belongs to the affected project | `ProductCapitalValuation.clean` + evaluation view |
| Value-only: creates a `ProductCapitalValuation` row linking the product to a signed amount; **no** `InvoiceItem` and **no** movement line are created | `CapitalValuationOperation.add_valuation` + `ProductCapitalValuation` |
| Valuation delta: `(new_unit_price − current_unit_price) × quantity` | `Product.compute_valuation_delta` |
| Inventory value ▲/▼: `capital_delta()` sums the signed amounts (positive gain, negative loss) into `movement_state(...)["value"]` / `inventory_value()` | `capital_delta` + `movement_state` |
| Product status unchanged (stays ACTIVE — a valuation is a value write-up/down, not a status transition) | `Product.status` |

### 2.6 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Evaluation create view (computes the delta and creates the gain/loss) | `EvaluationCreateView` |
| POST parsing/validation | `OperationDataValidator` |
| Reverse view (reason required) | `operation_reverse_view` |
| Detail view (aggregate amount + reversal action; no payment/settlement UI) | `operation_detail_view` |
| URL: `/<pk>/evaluate/<product_pk>/` | |
| URL: `/<pk>/reverse/` | |
| URL: `/<pk>/detail/` | |
| Templates | |

### 2.7 Tests

| Concern | Test file |
|---------|-----------|
| Create branches (validation, no transactions, value ▲/▼, product ACTIVE, period assigned) | |
| Reverse branches (reversal record, no counter-tx, value restored, product stays ACTIVE) | |
| Coverage manifest (executable branch registry) | |

---

## 3. Money flow & entities

### Capital Gain (CG)

- **Source (role):** the single **System** entity (`is_system=True`). Virtual.
- **Destination (role):** the **Project** entity in the URL (`is_project=True`, `_dest_role="url"`). It must be `active=True`.
- **No transactions are created.** The gain is **value-only**: it increases the linked product's movement-based inventory value (`capital_delta` → `inventory_value()`), without changing quantity, fund balance, payables, receivables or `profit_loss()`.

### Capital Loss (CL)

- **Source (role):** the **Project** entity in the URL (`is_project=True`). It owns the product being written down.
- **Destination (role):** the single **System** entity (`is_system=True`). Virtual.
- **No transactions are created.** The loss is **value-only**: it decreases the linked product's movement-based inventory value (`capital_delta` → `inventory_value()`), without changing quantity, fund balance, payables, receivables or `profit_loss()`.

---

## 4. Settlement model

There is **no settlement model** for either variant — Capital Valuation does not inherit
the payment/settlement machinery. `amount_settled`, `is_fully_settled`,
`amount_remaining_to_settle`, `payment_transactions` do **not** exist on a
`CapitalValuationOperation`. The valuation is value-only.

---

## 5. Actions

### 5.1 `create`

Entry points: model `CapitalValuationOperation.save()` with `operation_type=CAPITAL_GAIN`
(gain) or `CAPITAL_LOSS` (loss) (tests), or the evaluation view
(`EvaluationCreateView.post()` computes the delta and calls `Operation.create()` on the proxy).

#### 5.1.1 Validation branches — Capital Gain (CG)

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| CG1 | Source is System | `source.is_system` | `ValidationError` | `"Capital Gain source must be the System entity."` | `clean_source` | `CapitalGainCreateTest.test_source_must_be_system_entity` · `test_source_world_entity_raises_validation_error` |
| CG2 | Destination is Project | `destination.is_project` | `ValidationError` | `"Capital Gain destination must be a Project entity."` | `clean_destination` | `CapitalGainCreateTest.test_destination_must_be_project_entity` · `test_destination_world_entity_raises_validation_error` |
| CG3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | `Operation.clean()` | structural (System is always active) |
| CG4 | Destination entity active | `destination.active` | `ValidationError` | same as CG3 | `Operation.clean()` | `CapitalGainCreateTest.test_destination_project_must_be_active` |
| CG5 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | `CapitalGainCreateTest.test_amount_zero_raises_validation_error` · `test_amount_negative_raises_validation_error` |
| CG6 | Officer is staff + active | `officer.is_staff` and `officer.is_active` | `ValidationError` | officer errors | `OfficerMixin` | `CapitalGainCreateTest.test_officer_user_must_be_staff` · `test_officer_must_be_active` |
| CG7 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | `Operation.clean()` | shared period suite (`OperationPeriodAssignmentTest.test_operation_in_closed_period_raises`) |
| CG8 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | `Operation.save()` | shared period suite (`OperationPeriodAssignmentTest.test_operation_raises_when_no_open_period`) |
| CG9 | Material delta | `abs(delta) ≥ 0.01` | no operation recorded | `"No material change — no operation recorded."` | `EvaluationCreateView` | view contract (see §8) |
| CG10 | Ownership — product belongs to destination project | `product.entity == destination project` | `ValidationError` | `"Product '%(p)s' does not belong to '%(entity)s' and cannot be evaluated."` | `EvaluationCreateView` + `save_inventory` | `EvaluationOwnershipTest.test_evaluation_form_restricts_products_to_owned_entity` · `test_evaluation_post_rejects_other_project_product` · `test_evaluation_post_accepts_owned_product_form` |

#### 5.1.2 Success effects — Capital Gain (CG)

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| CG11 | No transactions created | `get_all_transactions().count() == 0` (no issuance, no payment) | (no transaction mixins) | `CapitalGainCreateTest.test_save_creates_no_transactions` |
| CG12 | No settlement machinery | `amount_settled`/`is_fully_settled`/`create_payment_transaction` absent | (no payment mixin) | `CapitalGainCreateTest.test_period_is_assigned_and_no_settlement_machinery` |
| CG13 | No cash flow — project fund unchanged | `project.balance` unchanged by the gain | `Entity.balance_at` | `CapitalGainCreateTest.test_project_fund_unchanged_by_gain_amount` |
| CG14 | Inventory value ▲ | `Product.current_value`/`inventory_value` increases by the gain (`capital_delta`) | `capital_delta()` + `Product.current_value` | `ProductCapitalValuationModelTest.test_inventory_value_rises_by_gain` · `test_movement_state_value_rises_by_gain` |
| CG15 | Value-only — no movement line | the gain creates a `ProductCapitalValuation` row linked to the product but **no** `InvoiceItem` and **no** `InventoryMovementLine` | `CapitalValuationOperation.add_valuation` + `ProductCapitalValuation` | `ProductCapitalValuationModelTest.test_gain_creates_valuation_row_no_invoice_no_movement` |
| CG16 | Product stays ACTIVE | the gain is a value write-up, not a status transition | `Product.status` | `CapitalGainReversalProductStatusTest.test_gain_and_reversal_keep_product_active` · `ProductTest.test_status_active_after_capital_gain` |
| CG17 | Period auto-assigned | `period` = the project's covering period | `Operation.save()` | shared period suite (`OperationPeriodAssignmentTest`) |
| CG18 | profit_loss unchanged | the gain is not an accounting transaction | `Entity.profit_loss` | structural (no accounting tx — see `OperationMixinSeparationTest`) |

#### 5.1.3 Validation branches — Capital Loss (CL)

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| CL1 | Source is a non-system project | `source.is_project` (system/world rejected) | `ValidationError` | `"Capital Loss source must be a Project entity."` | `clean_source` | `CapitalLossCreateTest.test_source_system_entity_raises_validation_error` |
| CL2 | Destination is System | `destination.is_system` | `ValidationError` | `"Capital Loss destination must be the System entity."` | `clean_destination` | `CapitalLossCreateTest.test_destination_must_be_system_entity` · `test_destination_world_entity_raises_validation_error` |
| CL3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | `Operation.clean()` | `CapitalLossCreateTest.test_source_project_must_be_active` |
| CL4 | Destination entity active | `destination.active` | `ValidationError` | same as CL3 | `Operation.clean()` | structural (System is always active) |
| CL5 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | `CapitalLossCreateTest.test_amount_zero_raises_validation_error` · `test_amount_negative_raises_validation_error` |
| CL6 | Officer is staff + active | `officer.is_staff` and `officer.is_active` | `ValidationError` | officer errors | `OfficerMixin` | `CapitalLossCreateTest.test_officer_user_must_be_staff` · `test_officer_must_be_active` |
| CL7 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | `Operation.clean()` | shared period suite (`OperationPeriodAssignmentTest.test_operation_in_closed_period_raises`) |
| CL8 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | `Operation.save()` | shared period suite (`OperationPeriodAssignmentTest.test_operation_raises_when_no_open_period`) |
| CL9 | Material delta | `abs(delta) ≥ 0.01` | no operation recorded | `"No material change — no operation recorded."` | `EvaluationCreateView` | view contract (see §8) |
| CL10 | Ownership — product belongs to source project | `product.entity == source project` | `ValidationError` | `"Product '%(p)s' does not belong to '%(entity)s' and cannot be evaluated."` | `EvaluationCreateView` + `save_inventory` | `EvaluationOwnershipTest.test_evaluation_form_restricts_products_to_owned_entity` · `test_evaluation_post_rejects_other_project_product` · `test_evaluation_post_accepts_owned_product_form` |

#### 5.1.4 Success effects — Capital Loss (CL)

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| CL11 | No transactions created | `get_all_transactions().count() == 0` (no issuance, no payment) | (no transaction mixins) | `CapitalLossCreateTest.test_save_creates_no_transactions` |
| CL12 | No settlement machinery | `amount_settled`/`is_fully_settled`/`create_payment_transaction` absent | (no payment mixin) | `CapitalLossCreateTest.test_period_is_assigned_and_no_settlement_machinery` |
| CL13 | No cash flow — project fund unchanged | `project.balance` unchanged by the loss (even a zero-balance or deficit project) | `Entity.balance_at` | `CapitalLossCreateTest.test_project_fund_unchanged_by_loss_amount` · `test_zero_balance_project_can_record_capital_loss` · `test_loss_larger_than_balance_is_allowed_non_cash` · `test_loss_making_project_can_record_further_losses` |
| CL14 | Inventory value ▼ | `Product.current_value`/`inventory_value` decreases by the loss (`capital_delta`) | `capital_delta()` + `Product.current_value` | `ProductCapitalValuationModelTest.test_movement_state_value_falls_by_loss` |
| CL15 | Value-only — no movement line | the loss creates a `ProductCapitalValuation` row linked to the product but **no** `InvoiceItem` and **no** `InventoryMovementLine` | `CapitalValuationOperation.add_valuation` + `ProductCapitalValuation` | `CapitalLossCreateTest.test_capital_loss_is_value_only_no_movement_line` · `ProductCapitalValuationModelTest.test_loss_requires_negative_amount` |
| CL16 | Product stays ACTIVE | the loss is a value write-down, not a status transition | `Product.status` | `CapitalLossReversalProductStatusTest.test_loss_and_reversal_keep_product_active` · `ProductTest.test_status_active_after_capital_loss` |
| CL17 | Period auto-assigned | `period` = the project's covering period | `Operation.save()` | shared period suite (`OperationPeriodAssignmentTest`) |
| CL18 | profit_loss unchanged | the loss is not an accounting transaction | `Entity.profit_loss` | structural (no accounting tx — see `OperationMixinSeparationTest`) |

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).
The reversal mechanics are identical for both variants (same `ReversableModel` machinery);
tests pin each variant separately.

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| CG19/CL19 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | `ReversableModel._validate_can_be_reversed` + view guard | `CapitalGainReversalTest.test_cannot_reverse_already_reversed_operation` · `CapitalLossReversalTest.test_cannot_reverse_already_reversed_operation` |
| CG20/CL20 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | `ReversableModel._validate_can_be_reversed` + view guard | `CapitalGainReversalTest.test_cannot_reverse_a_reversal` · `CapitalLossReversalTest.test_cannot_reverse_a_reversal` |
| CG21/CL21 | No non-reversed adjustments | n/a — not adjustable | never fails | — | `is_adjustable=False` | n/a |
| CG22/CL22 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | `operation_reverse_view` | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| CG23/CL23 | Reversal record created | cloned op, `reversal_of = original` | `ReversableModel.reverse()` | `CapitalGainReversalTest.test_reverse_creates_reversal_operation` · `CapitalLossReversalTest.test_reverse_creates_reversal_operation` |
| CG24/CL24 | Original marked reversed | `original.reversed_by = reversal` | `ReversableModel.reverse()` | `CapitalGainReversalTest.test_reverse_marks_original_as_reversed` · `CapitalLossReversalTest.test_reverse_marks_original_as_reversed` |
| CG25/CL25 | Reversal inherits identity | `amount`, `source`, `destination` copied; `is_reversal=True`, `is_reversed=False` | `ReversableModel._get_reverse_kwargs` | `CapitalGainReversalTest.test_reverse_inherits_amount_source_destination` · `test_reversal_is_reversal` · `CapitalLossReversalTest.test_reverse_inherits_amount_source_destination` · `test_reversal_is_reversal` |
| CG26/CL26 | No counter-transactions | neither the original nor its reversal owns any `Transaction` | (no transaction mixins) | `CapitalGainReversalTest.test_reverse_creates_no_transactions` · `CapitalLossReversalTest.test_reverse_creates_no_transactions` |
| CG27/CL27 | Inventory value restored | the reversed valuation is excluded from `capital_delta()` (filtered on `reversed_by__isnull=True`) → `inventory_value()` returns to baseline | `capital_delta` | `ProductCapitalValuationModelTest.test_reverse_restores_value_to_baseline` · `test_reverse_restores_inventory_value` |
| CG28/CL28 | Product stays ACTIVE | the reversal is a value write-down/write-up back to baseline, not a status transition | `Product.status` | `CapitalGainReversalProductStatusTest.test_gain_and_reversal_keep_product_active` · `CapitalLossReversalProductStatusTest.test_loss_and_reversal_keep_product_active` |
| CG29/CL29 | Fund unchanged after reversal | `project.balance` unchanged | `Entity.balance_at` | `CapitalGainReversalTest.test_project_fund_unchanged_after_reversal` · `CapitalLossReversalTest.test_project_fund_unchanged_after_reversal` |
| CG30/CL30 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger, inventory value) | whole engine | `CapitalGainReversalTest.test_create_then_reverse_leaves_world_unchanged` · `CapitalLossReversalTest.test_create_then_reverse_leaves_world_unchanged` |

### 5.3 `pay`

There is **no pay action** for either variant — it has no payment machinery at all
(`create_payment_transaction` does not exist on the class). Payment-related code is never
reachable.

### 5.4 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by `ImmutableMixin` via `_immutable_fields`. Shared with every operation (see [`op_1`](op_1_cash_injection.md) §5.4).

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — `Entity.save()`.
- The operation's governing entity (`period_entity`) is the **project** — for a gain it is the **destination** (`_dest_role = "url"`); for a loss it is the **source** (`_source_role = "url"`). The System (virtual) has no periods and is exempt.
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (CG8/CL8).
- New operations dated inside a **closed** period are rejected (CG7/CL7).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period (`_reverse_period`).

---

## 7. Entity roles & balance contract

### Capital Gain (CG)

- System is the only allowed source; Project the only allowed destination — enforced at model (CG1/CG2).
- No transactions → the project's fund balance, payables and receivables are **never** affected by a gain.
- The gain is value-only: it raises `inventory_value()` (via `capital_delta`) and therefore `FinancialPeriod.end_assets`; it is **not** recognized in `profit_loss()`.

### Capital Loss (CL)

- Project is the only allowed source; System the only allowed destination — enforced at model (CL1/CL2).
- No transactions → the project's fund balance, payables and receivables are **never** affected by a loss.
- **No fund-balance requirement** — a project with a zero or insufficient balance may still record a capital loss; a loss-making project can go further into deficit.
- The loss is value-only: it lowers `inventory_value()` (via `capital_delta`) and therefore `FinancialPeriod.end_assets`; it is **not** recognized in `profit_loss()`.

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Create route | `GET/POST /<project_pk>/evaluate/<product_pk>/` → `EvaluationCreateView` |
| Product | the evaluated product (owned by the project), with its current value shown |
| Delta | `(new_unit_price − current_unit_price) × quantity`; no material change (< 0.01) records nothing (CG9/CL9) |
| Category | hidden (no category) |
| Amount | the absolute valuation delta, validated > 0 at model |
| POST parsing | `OperationDataValidator` — date format, description, category (n/a), `amount_paid` (n/a, forced 0) |
| Valuation | the view computes the signed delta, creates the operation (selecting `CAPITAL_GAIN` when `delta > 0`, `CAPITAL_LOSS` otherwise), then `CapitalValuationOperation.add_valuation(product, amount)` records the signed `ProductCapitalValuation` row |
| List entry | not in the operations-list "New Operation" dropdown — entered from the stock detail "Record Evaluation" button |
| Detail | `operation_detail_view` — shows the operation total + a **Capital Valuations** section (product, signed amount, date, officer) + reversal action; **no** payment/settlement sections (rendered as one-shot) |
| Valuations list | `invoice_items_list_view` renders the capital-valuation list for `has_capital_valuation` operations instead of an invoice-items table |
| Reverse | `operation_reverse_view` — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (CG19/CG20, CL19/CL20) |

---

## 9. Branch catalog (all possible branches)

**create — validation (CG):** CG1 source=system · CG2 dest=project · CG3 source active · CG4 dest active · CG5 amount>0 · CG6 officer staff+active · CG7 not closed-period · CG8 covering period exists · CG9 material delta · CG10 product ownership

**create — validation (CL):** CL1 source=project (non-system) · CL2 dest=system · CL3 source active · CL4 dest active · CL5 amount>0 · CL6 officer staff+active · CL7 not closed-period · CL8 covering period exists · CL9 material delta · CL10 product ownership

**create — effects (CG):** CG11 no transactions · CG12 no settlement machinery · CG13 no cash flow (fund unchanged) · CG14 inventory value ▲ · CG15 value-only (no movement line) · CG16 product ACTIVE · CG17 period assigned · CG18 profit_loss unchanged

**create — effects (CL):** CL11 no transactions · CL12 no settlement machinery · CL13 no cash flow (fund unchanged, even in deficit) · CL14 inventory value ▼ · CL15 value-only (no movement line) · CL16 product ACTIVE · CL17 period assigned · CL18 profit_loss unchanged

**reverse — validation:** CG19/CL19 not reversed · CG20/CL20 not a reversal · CG21/CL21 no adjustments (n/a) · CG22/CL22 reason required (view)

**reverse — effects:** CG23/CL23 reversal record · CG24/CL24 original reversed · CG25/CL25 identity copied · CG26/CL26 no counter-txs · CG27/CL27 inventory value restored · CG28/CL28 product stays ACTIVE · CG29/CL29 fund unchanged · CG30/CL30 differential invariant

**immutability:** IM1/IM2/IM3 source/destination/amount immutable

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| No transactions | `CapitalGainCreateTest.test_save_creates_no_transactions` · `CapitalLossCreateTest.test_save_creates_no_transactions` | CG11, CL11 |
| No settlement machinery | `CapitalGainCreateTest.test_period_is_assigned_and_no_settlement_machinery` · `CapitalLossCreateTest.test_period_is_assigned_and_no_settlement_machinery` | CG12, CL12 |
| Source validation | `CapitalGainCreateTest.test_source_must_be_system_entity` · `test_source_world_entity_raises_validation_error` · `CapitalLossCreateTest.test_source_system_entity_raises_validation_error` · `test_source_project_must_be_active` | CG1, CG3, CL1, CL3 |
| Destination validation | `CapitalGainCreateTest.test_destination_must_be_project_entity` · `test_destination_world_entity_raises_validation_error` · `test_destination_project_must_be_active` · `CapitalLossCreateTest.test_destination_must_be_system_entity` · `test_destination_world_entity_raises_validation_error` | CG2, CG4, CL2 |
| Amount | `CapitalGainCreateTest.test_amount_zero_raises_validation_error` · `test_amount_negative_raises_validation_error` · `CapitalLossCreateTest.test_amount_zero_raises_validation_error` · `test_amount_negative_raises_validation_error` | CG5, CL5 |
| Officer | `CapitalGainCreateTest.test_officer_user_must_be_staff` · `test_officer_must_be_active` · `CapitalLossCreateTest.test_officer_user_must_be_staff` · `test_officer_must_be_active` | CG6, CL6 |
| Ownership (evaluation) | `EvaluationOwnershipTest.test_evaluation_post_rejects_other_project_product` · `test_evaluation_post_accepts_owned_product_form` | CG10, CL10 |
| No cash flow / fund unchanged | `CapitalGainCreateTest.test_project_fund_unchanged_by_gain_amount` · `CapitalLossCreateTest.test_project_fund_unchanged_by_loss_amount` · `test_zero_balance_project_can_record_capital_loss` · `test_loss_larger_than_balance_is_allowed_non_cash` · `test_loss_making_project_can_record_further_losses` | CG13, CL13 |
| Inventory value ▲/▼ | `ProductCapitalValuationModelTest.test_inventory_value_rises_by_gain` · `test_movement_state_value_rises_by_gain` · `test_movement_state_value_falls_by_loss` | CG14, CL14 |
| Value-only (no movement line) | `ProductCapitalValuationModelTest.test_gain_creates_valuation_row_no_invoice_no_movement` · `CapitalLossCreateTest.test_capital_loss_is_value_only_no_movement_line` · `ProductCapitalValuationModelTest.test_loss_requires_negative_amount` | CG15, CL15 |
| Product stays ACTIVE | `CapitalGainReversalProductStatusTest.test_gain_and_reversal_keep_product_active` · `ProductTest.test_status_active_after_capital_gain` · `CapitalLossReversalProductStatusTest.test_loss_and_reversal_keep_product_active` · `ProductTest.test_status_active_after_capital_loss` | CG16, CG28, CL16, CL28 |
| Period assigned | shared period suite (`OperationPeriodAssignmentTest`) | CG17, CL17 |
| Reversal — no counter-txs | `CapitalGainReversalTest.test_reverse_creates_no_transactions` · `CapitalLossReversalTest.test_reverse_creates_no_transactions` | CG26, CL26 |
| Valuation restored on reverse | `ProductCapitalValuationModelTest.test_reverse_restores_value_to_baseline` · `test_reverse_restores_inventory_value` | CG27, CL27 |
| Differential invariant | `CapitalGainReversalTest.test_create_then_reverse_leaves_world_unchanged` · `CapitalLossReversalTest.test_create_then_reverse_leaves_world_unchanged` | CG30, CL30 |
| Reverse constraints | `CapitalGainReversalTest.test_cannot_reverse_already_reversed_operation` · `test_cannot_reverse_a_reversal` · `CapitalLossReversalTest.test_cannot_reverse_already_reversed_operation` · `test_cannot_reverse_a_reversal` | CG19, CG20, CL19, CL20 |
| Immutability | `CapitalGainCreateTest.test_source_is_immutable` · `test_destination_is_immutable` · `test_amount_is_immutable` · `CapitalLossCreateTest.test_source_is_immutable` · `test_destination_is_immutable` · `test_amount_is_immutable` | IM1–IM3 |
| Can't be paid | `CapitalGainCreateTest.test_cannot_be_paid` · `test_check_balance_on_payment_is_disabled` · `CapitalLossCreateTest.test_cannot_be_paid` · `test_check_balance_on_payment_is_disabled` | BP1 |
