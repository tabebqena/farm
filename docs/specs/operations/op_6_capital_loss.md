# Capital Loss — Operation Contract

**Epic:** 10.3 — Miscellaneous One-Shot Operations (stock event)
**Type:** Stock event (no accounting transactions), value-only
**Actions:** `create`, `reverse`
**Contract status:** v3 — Capital Loss is a **stock event**, not an accounting operation: it creates **no** `Transaction` rows, has no payment/settlement machinery, and is still assigned to a financial period (and blocked inside a closed one). It is **value-only** — it lowers the linked product's movement-based inventory value without changing quantity, fund balance or `profit_loss()`.

> **Primary source of contract.** This document is the authoritative contract for the **Capital Loss** operation.
> Every clause below names its implementing code (model → mixin → view) and its pinning test — as plain names, never links, so renames do not break the spec.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> See [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md) for the shared structure and
> [`op_1_cash_injection.md`](op_1_cash_injection.md) for a fully worked example.
> The inventory value this operation lowers is the movement-based [`stock.md`](../features/stock.md) contract (`capital_delta` → `movement_state["value"]`) — keep that spec in sync when this operation's valuation behavior changes.

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.CAPITAL_LOSS` (`"CAPITAL_LOSS"`) | |
| Proxy class | `CapitalValuationOperation` | |
| URL slug | `"capital-loss"` | |
| Label | `"Capital Loss Issuance"` | |
| Source role | `url` (must be a Project) | |
| Destination role | `system` | |
| Registered in | `PROXY_MAP` | |
| Cross-op reference | row CL | [`operations-comparison.md`](operations-comparison.md) |

> **Shared proxy.** Capital Gain and Capital Loss are served by a **single** proxy,
> `CapitalValuationOperation`, which dispatches per-type configuration (roles, label,
> URL slug, validation) on the row's `operation_type` — the same pattern as
> `CorrectionOperation` for correction credit/debit. Both `"capital-gain"` and
> `"capital-loss"` URL slugs resolve to this one proxy. Nothing about Capital Loss's
> behavior changes: it remains a value-only stock event.

**Configuration flags**:

| Flag | Value | Meaning |
|------|-------|---------|
| `can_pay` | `False` | no payment action |
| `is_partially_payable` | `False` | n/a (no settlement) |
| `check_balance_on_payment` | `False` | n/a (no payment) |
| `has_category` / `category_required` | `False` | no financial category |
| `has_repayment` | `False` | no repayment action |
| `has_invoice` | `False` | no invoice items — the loss is recorded on a dedicated valuation row, not on an `InvoiceItem` |
| `has_capital_valuation` | `True` | the loss is a `ProductCapitalValuation` row linking the owned product to a signed (negative) amount (value-only — no movement line) |

> **No accounting mixins.** `CapitalValuationOperation` (the shared Capital Gain/Loss
> proxy) inherits only `ImmutableMixin`, `AmountCleanMixin`, `OfficerMixin`,
> `ReversableModel`, `BaseModel` (via the lean `Operation` base). It does **not** inherit
> `LinkedIssuanceTransactionMixin`, `LinkedPaymentTransactionMixin`,
> `LinkedRePaymentTransactionMixin` or `AdjustableMixin` — so no transactions, no settlement,
> no repayment, no adjustments, no P&L entry in `profit_loss()`.

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row names the code that must honor it (plain names, no links).

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_destination` | |
| Proxy registry / URL→class resolution | |
| Shared `Operation` engine (`clean`, `save`, `reverse`, `create`, `resolve_request`, `save_inventory`, period assignment, reversable tx types) | |
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
| **None** — Capital Loss creates no `Transaction` rows | (no transaction mixins inherited) |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Fund balance never affected (no payment) | `Entity.balance_at` (no Capital Loss tx types) |
| P&L not affected — value flows through inventory | `Entity.profit_loss` (Capital Loss no longer a cost) |
| Open financial period auto-created on entity creation | `Entity.save()` |

### 2.5 Inventory layer (capital-specific)

| Concern | Implementing code |
|---------|-------------------|
| Ownership guard: the evaluated product belongs to the source project | `ProductCapitalValuation.clean` + evaluation view |
| Value-only: creates a `ProductCapitalValuation` row linking the product to a signed (negative) amount; **no** `InvoiceItem` and **no** movement line are created | `CapitalValuationOperation.add_valuation` + `ProductCapitalValuation` |
| Valuation delta: `(new_unit_price − current_unit_price) × quantity` | `Product.compute_valuation_delta` |
| Inventory value ▼: `capital_delta()` sums the signed amounts (negative loss) into `movement_state(...)["value"]` / `inventory_value()` | `capital_delta` + `movement_state` |
| Product status unchanged (stays ACTIVE — a loss is a value write-down, not a status transition) | `Product.status` |

### 2.6 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Evaluation create view (computes the delta and creates the loss) | `EvaluationCreateView` |
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
| Create branches (validation, no transactions, value ▼, product ACTIVE, period assigned) | |
| Reverse branches (reversal record, no counter-tx, value restored, product stays ACTIVE) | |
| Coverage manifest (executable branch registry) | |

---

## 3. Money flow & entities

- **Source (role):** the **Project** entity in the URL (`is_project=True`). It owns the product being written down.
- **Destination (role):** the single **System** entity (`is_system=True`). Virtual.
- **No transactions are created.** The loss is **value-only**: it decreases the linked product's movement-based inventory value (`capital_delta` → `inventory_value()`), without changing quantity, fund balance, payables, receivables or `profit_loss()`.

---

## 4. Settlement model

There is **no settlement model** — Capital Loss does not inherit the payment/settlement
machinery. `amount_settled`, `is_fully_settled`, `amount_remaining_to_settle`,
`payment_transactions` do **not** exist on a `CapitalLossOperation`. The loss is value-only.

---

## 5. Actions

### 5.1 `create`

Entry points: model `CapitalValuationOperation.save()` (tests) or the evaluation view
(`EvaluationCreateView.post()` computes the delta and calls `Operation.create()` on the proxy).

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source is a non-system project | `source.is_project` (system/world rejected) | `ValidationError` | `"Capital Loss source must be a Project entity."` | `clean_source` | `CapitalLossCreateTest.test_source_system_entity_raises_validation_error` |
| VC2 | Destination is System | `destination.is_system` | `ValidationError` | `"Capital Loss destination must be the System entity."` | `clean_destination` | `CapitalLossCreateTest.test_destination_must_be_system_entity` · `test_destination_world_entity_raises_validation_error` |
| VC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | `Operation.clean()` | `CapitalLossCreateTest.test_source_project_must_be_active` |
| VC4 | Destination entity active | `destination.active` | `ValidationError` | same as VC3 | `Operation.clean()` | structural (System is always active) |
| VC5 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | `CapitalLossCreateTest.test_amount_zero_raises_validation_error` · `test_amount_negative_raises_validation_error` |
| VC6 | Officer is staff + active | `officer.is_staff` and `officer.is_active` | `ValidationError` | officer errors | `OfficerMixin` | `CapitalLossCreateTest.test_officer_user_must_be_staff` · `test_officer_must_be_active` |
| VC7 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | `Operation.clean()` | shared period suite (`OperationPeriodAssignmentTest.test_operation_in_closed_period_raises`) |
| VC8 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | `Operation.save()` | shared period suite (`OperationPeriodAssignmentTest.test_operation_raises_when_no_open_period`) |
| VC9 | Material delta | `abs(delta) ≥ 0.01` | no operation recorded | `"No material change — no operation recorded."` | `EvaluationCreateView` | view contract (see §8) |
| VC10 | Ownership — product belongs to source project | `product.entity == source project` | `ValidationError` | `"Product '%(p)s' does not belong to '%(entity)s' and cannot be evaluated."` | `EvaluationCreateView` + `save_inventory` | `EvaluationOwnershipTest.test_evaluation_form_restricts_products_to_owned_entity` · `test_evaluation_post_rejects_other_project_product` · `test_evaluation_post_accepts_owned_product_form` |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | No transactions created | `get_all_transactions().count() == 0` (no issuance, no payment) | (no transaction mixins) | `CapitalLossCreateTest.test_save_creates_no_transactions` |
| SC2 | No settlement machinery | `amount_settled`/`is_fully_settled`/`create_payment_transaction` absent | (no payment mixin) | `CapitalLossCreateTest.test_period_is_assigned_and_no_settlement_machinery` |
| SC3 | No cash flow — project fund unchanged | `project.balance` unchanged by the loss (even a zero-balance or deficit project) | `Entity.balance_at` | `CapitalLossCreateTest.test_project_fund_unchanged_by_loss_amount` · `test_zero_balance_project_can_record_capital_loss` · `test_loss_larger_than_balance_is_allowed_non_cash` · `test_loss_making_project_can_record_further_losses` |
| SC4 | Inventory value ▼ | `Product.current_value`/`inventory_value` decreases by the loss (`capital_delta`) | `capital_delta()` + `Product.current_value` | `ProductCapitalValuationModelTest.test_movement_state_value_falls_by_loss` |
| SC5 | Value-only — no movement line | the loss creates a `ProductCapitalValuation` row linked to the product but **no** `InvoiceItem` and **no** `InventoryMovementLine` | `CapitalLossOperation.add_valuation` + `ProductCapitalValuation` | `CapitalLossCreateTest.test_capital_loss_is_value_only_no_movement_line` · `ProductCapitalValuationModelTest.test_loss_requires_negative_amount` |
| SC6 | Product stays ACTIVE | the loss is a value write-down, not a status transition | `Product.status` | `CapitalLossReversalProductStatusTest.test_loss_and_reversal_keep_product_active` · `ProductTest.test_status_active_after_capital_loss` |
| SC7 | Period auto-assigned | `period` = the project's covering period | `Operation.save()` | shared period suite (`OperationPeriodAssignmentTest`) |
| SC8 | profit_loss unchanged | the loss is not an accounting transaction | `Entity.profit_loss` | structural (no accounting tx — see `OperationMixinSeparationTest`) |

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | `ReversableModel._validate_can_be_reversed` + view guard | `CapitalLossReversalTest.test_cannot_reverse_already_reversed_operation` |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | `ReversableModel._validate_can_be_reversed` + view guard | `CapitalLossReversalTest.test_cannot_reverse_a_reversal` |
| VR3 | No non-reversed adjustments | n/a — Capital Loss is not adjustable | never fails | — | `is_adjustable=False` | n/a |
| VR4 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | `operation_reverse_view` | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | `ReversableModel.reverse()` | `CapitalLossReversalTest.test_reverse_creates_reversal_operation` |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | `ReversableModel.reverse()` | `CapitalLossReversalTest.test_reverse_marks_original_as_reversed` |
| SR3 | Reversal inherits identity | `amount`, `source`, `destination` copied; `is_reversal=True`, `is_reversed=False` | `ReversableModel._get_reverse_kwargs` | `CapitalLossReversalTest.test_reverse_inherits_amount_source_destination` · `test_reversal_is_reversal` |
| SR4 | No counter-transactions | neither the original nor its reversal owns any `Transaction` | (no transaction mixins) | `CapitalLossReversalTest.test_reverse_creates_no_transactions` |
| SR5 | Inventory value restored | the reversed loss is excluded from `capital_delta()` (filtered on `reversed_by__isnull=True`) → `inventory_value()` returns to baseline | `capital_delta` | `ProductCapitalValuationModelTest.test_reverse_restores_value_to_baseline` · `test_reverse_restores_inventory_value` |
| SR6 | Product stays ACTIVE | the reversal is a value write-up back to baseline, not a status transition | `Product.status` | `CapitalLossReversalProductStatusTest.test_loss_and_reversal_keep_product_active` |
| SR7 | Fund unchanged after reversal | `project.balance` unchanged | `Entity.balance_at` | `CapitalLossReversalTest.test_project_fund_unchanged_after_reversal` |
| SR8 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger, inventory value) | whole engine | `CapitalLossReversalTest.test_create_then_reverse_leaves_world_unchanged` |

### 5.3 `pay`

There is **no pay action** for Capital Loss — it has no payment machinery at all
(`create_payment_transaction` does not exist on the class). Payment-related code is never
reachable.

### 5.4 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by `ImmutableMixin` via `_immutable_fields`. Shared with every operation (see [`op_1`](op_1_cash_injection.md) §5.4).

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — `Entity.save()`.
- The operation's governing entity (`period_entity`) is the **source project** (`_source_role = "url"`) — `Operation.period_entity`. The System (virtual) has no periods and is exempt.
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC8).
- New operations dated inside a **closed** period are rejected (VC7).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period (`_reverse_period`).

---

## 7. Entity roles & balance contract

- Project is the only allowed source; System the only allowed destination — enforced at model (VC1/VC2).
- No transactions → the project's fund balance, payables and receivables are **never** affected by a loss.
- **No fund-balance requirement** — a project with a zero or insufficient balance may still record a capital loss; a loss-making project can go further into deficit.
- The loss is value-only: it lowers `inventory_value()` (via `capital_delta`) and therefore `FinancialPeriod.end_assets`; it is **not** recognized in `profit_loss()`.

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Create route | `GET/POST /<project_pk>/evaluate/<product_pk>/` → `EvaluationCreateView` |
| Product | the evaluated product (owned by the project), with its current value shown |
| Delta | `(new_unit_price − current_unit_price) × quantity`; no material change (< 0.01) records nothing (VC9) |
| Category | hidden (no category) |
| Amount | the absolute valuation delta, validated > 0 at model |
| POST parsing | `OperationDataValidator` — date format, description, category (n/a), `amount_paid` (n/a, forced 0) |
| Valuation | the view computes the signed delta, creates the operation, then `CapitalValuationOperation.add_valuation(product, amount)` records the `ProductCapitalValuation` row |
| List entry | not in the operations-list "New Operation" dropdown — entered from the stock detail "Record Evaluation" button |
| Detail | `operation_detail_view` — shows the operation total + a **Capital Valuations** section (product, signed amount, date, officer) + reversal action; **no** payment/settlement sections (rendered as one-shot) |
| Valuations list | `invoice_items_list_view` renders the capital-valuation list for `has_capital_valuation` operations instead of an invoice-items table |
| Reverse | `operation_reverse_view` — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source=project (non-system) · VC2 dest=system · VC3 source active · VC4 dest active · VC5 amount>0 · VC6 officer staff+active · VC7 not closed-period · VC8 covering period exists · VC9 material delta · VC10 product ownership

**create — effects:** SC1 no transactions · SC2 no settlement machinery · SC3 no cash flow (fund unchanged, even in deficit) · SC4 inventory value ▼ · SC5 value-only (no movement line) · SC6 product ACTIVE · SC7 period assigned · SC8 profit_loss unchanged

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no adjustments (n/a) · VR4 reason required (view)

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 identity copied · SR4 no counter-txs · SR5 inventory value restored · SR6 product stays ACTIVE · SR7 fund unchanged · SR8 differential invariant

**immutability:** IM1/IM2/IM3 source/destination/amount immutable

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| No transactions | `CapitalLossCreateTest.test_save_creates_no_transactions` | SC1 |
| No settlement machinery | `CapitalLossCreateTest.test_period_is_assigned_and_no_settlement_machinery` | SC2 |
| Source validation | `CapitalLossCreateTest.test_source_system_entity_raises_validation_error` · `test_source_project_must_be_active` | VC1, VC3 |
| Destination validation | `CapitalLossCreateTest.test_destination_must_be_system_entity` · `test_destination_world_entity_raises_validation_error` | VC2 |
| Amount | `CapitalLossCreateTest.test_amount_zero_raises_validation_error` · `test_amount_negative_raises_validation_error` | VC5 |
| Officer | `CapitalLossCreateTest.test_officer_user_must_be_staff` · `test_officer_must_be_active` | VC6 |
| Ownership (evaluation) | `EvaluationOwnershipTest.test_evaluation_post_rejects_other_project_product` · `test_evaluation_post_accepts_owned_product_form` | VC10 |
| No cash flow / fund unchanged (deficit allowed) | `CapitalLossCreateTest.test_project_fund_unchanged_by_loss_amount` · `test_zero_balance_project_can_record_capital_loss` · `test_loss_larger_than_balance_is_allowed_non_cash` · `test_loss_making_project_can_record_further_losses` | SC3 |
| Inventory value ▼ | `ProductCapitalValuationModelTest.test_movement_state_value_falls_by_loss` | SC4 |
| Value-only (no movement line) | `CapitalLossCreateTest.test_capital_loss_is_value_only_no_movement_line` · `ProductCapitalValuationModelTest.test_loss_requires_negative_amount` | SC5 |
| Product stays ACTIVE | `CapitalLossReversalProductStatusTest.test_loss_and_reversal_keep_product_active` · `ProductTest.test_status_active_after_capital_loss` | SC6, SR6 |
| Period assigned | shared period suite (`OperationPeriodAssignmentTest`) | SC7 |
| Reversal — no counter-txs | `CapitalLossReversalTest.test_reverse_creates_no_transactions` | SR4 |
| Valuation restored on reverse | `ProductCapitalValuationModelTest.test_reverse_restores_value_to_baseline` · `test_reverse_restores_inventory_value` | SR5 |
| Differential invariant | `CapitalLossReversalTest.test_create_then_reverse_leaves_world_unchanged` | SR8 |
| Reverse constraints | `CapitalLossReversalTest.test_cannot_reverse_already_reversed_operation` · `test_cannot_reverse_a_reversal` | VR1, VR2 |
| Immutability | `CapitalLossCreateTest.test_source_is_immutable` · `test_destination_is_immutable` · `test_amount_is_immutable` | IM1–IM3 |
| Can't be paid | `CapitalLossCreateTest.test_cannot_be_paid` · `test_check_balance_on_payment_is_disabled` | BP1 |
