# Expense — Operation Contract

**Epic:** 11.3 — Payable Operations
**Type:** Multi-stage, partially payable, category-required
**Actions:** `create`, `pay`, `adjust`, `reverse`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Expense** operation.
> Every clause below names its implementing code (model → mixin → transaction → view) and its pinning test — as plain names, never links, so renames do not break the spec.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> Other operations follow the same structure — see [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md) and
> [`op_1_cash_injection.md`](op_1_cash_injection.md) for a fully worked example.

**Concept:** Records an obligation to pay for a service or product purchased from an unregistered (world) vendor. The expense carries a `FinancialCategory` (type `EXPENSE`) so it can be filtered/grouped later. The destination is always the **World** entity and the issuance is **unguarded** — the project payables increase by the issuance amount, and only the individual payments are balance-guarded.

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.EXPENSE` (`"EXPENSE"`) | |
| Proxy class | `ExpenseOperation` | |
| URL slug | `"expense"` | |
| Label | `"Expense Issuance"` | |
| Theme | n/a (not defined on the proxy) | — |
| Source role | `url` (must be a Project) | |
| Destination role | `world` | |
| Registered in | `PROXY_MAP` | |

**Configuration flags**:

| Flag | Value | Meaning |
|------|-------|---------|
| `_issuance_transaction_type` | `EXPENSE_ISSUANCE` | issuance tx created on save (obligation record) |
| `_payment_transaction_type` | `EXPENSE_PAYMENT` | payment tx created via the standalone `pay` action |
| `_is_one_shot_operation` | `False` | no auto-payment on create; payments happen later via **pay** |
| `can_pay` | `True` | `process_payment()` / `create_payment_transaction()` are active |
| `is_partially_payable` | `True` | multiple partial payments allowed |
| `max_payment_transaction_count` | `-1` | unlimited number of payment txs |
| `check_balance_on_payment` | `True` | each payment is guarded against the project fund balance |
| `has_category` / `category_required` | `True` / `True` | financial category required (type `EXPENSE`) |
| `category_type` | `"EXPENSE"` | only `category_type="EXPENSE"` categories are valid |
| `has_repayment` | `False` | no repayment action |
| `has_invoice` | `False` | no invoice items / no inventory movements |
| `is_adjustable` / `is_items_adjustable` | `True` / `False` | amount-adjustable; no item-level adjustment |

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row names the code that must honor it (plain names, no links).

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_source`/`clean_destination` | |
| Proxy registry / URL→class resolution | |
| Shared `Operation` engine (`clean`, `save`, `create`, `reverse`, `resolve_request`, period assignment, category FK enforcement, reversable tx types) | |
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
| Standalone payment + per-payment balance guard + settlement | `LinkedPaymentTransactionMixin` |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | `ReversableModel` + `Operation.reverse()` |
| Adjustable effective amount | `AdjustableMixin` |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | |
| `EXPENSE_ISSUANCE` (project → world, non-cash, payables ▲) | |
| `EXPENSE_PAYMENT` (project → world, cash, payables ▼) | |
| `EXPENSE_ADJUSTMENT_INCREASE` (project → world, non-cash, payables ▲) | |
| `EXPENSE_ADJUSTMENT_DECREASE` (world → project, non-cash, payables ▼) | |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Project payables = issuance/adjustment-increase txs − payment/adjustment-decrease txs | `Entity.payables` → `payables_at` |
| Project receivables (unaffected by Expense) | `Entity.receivables` → `receivables_at` |
| World (virtual) never balance-checked | `Entity.can_pay` |
| Open financial period auto-created on entity creation | `Entity.save()` |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (generic, resolves URL project source + world destination, category dropdown) | `OperationCreateView` |
| POST parsing/validation (date, description, category, amount) | `OperationDataValidator` |
| Amount computation (raw POST field — no invoice formset) | `_compute_amount` |
| Category passed into `Operation.create()` | |
| Standalone pay view | `record_transaction_payment` |
| Adjust view (accounting adjustment for PURCHASE/SALE/EXPENSE) | `record_accounting_adjustment` |
| Reverse view (reason required) | `operation_reverse_view` |
| Detail view (transactions + settlement + reversal button) | `operation_detail_view` |
| URL: `/<pk>/<op_type>/create` | |
| URL: `payment/<pk>/create` (pay) | |
| URL: `/<pk>/adjustment-create` (adjust) | |
| URL: `/<pk>/detail/` | |
| URL: `/<pk>/reverse/` | |
| Templates | |

### 2.6 Tests

| Concern | Test file |
|---------|-----------|
| Create branches | |
| Pay branches | |
| Reverse branches | |
| Adjust branches (shared Purchase/Sale/Expense engine) | |
| Coverage manifest (executable branch registry) | |

---

## 3. Money flow & entities

- **Source (payer):** the **Project** entity in the URL (`is_project=True`, `_source_role="url"`). Its fund is the payment source fund — the real payer.
- **Destination (receiver):** the single **World** entity (`is_world=True`, `_dest_role="world"`). Virtual — never balance-checked, exempt from period checks (world has no periods).
- **Transaction flow:**

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `EXPENSE_ISSUANCE` (on create) | `project.fund → world.fund` | none (issuance, non-cash) — project **payables ▲** |
| 2 | `EXPENSE_PAYMENT` (on pay) | `project.fund → world.fund` | ▼ project fund; project **payables ▼** |
| 3 | `EXPENSE_ADJUSTMENT_INCREASE` (on adjust ↑) | `project.fund → world.fund` | none (non-cash) — project payables ▲ |
| 4 | `EXPENSE_ADJUSTMENT_DECREASE` (on adjust ↓) | `world.fund → project.fund` | none (non-cash) — project payables ▼ |

- **Payment source fund:** `self.source` (project)
- **Payment target fund:** `self.destination` (world)
---

## 4. Settlement model

Derived from `LinkedPaymentTransactionMixin` using **payment-type** transactions (`EXPENSE_PAYMENT`) only:

| Property | After create | After partial pay | After full pay | After reverse |
|----------|--------------|-------------------|----------------|---------------|
| `amount_settled` | `0.00` | partial sum | `== amount` | `0.00` |
| `total_settlable_amount` (`effective_amount`) | `== amount` | unchanged (until adjust) | unchanged | unchanged |
| `amount_remaining_to_settle` | `== amount` | decreases by each payment | `0.00` | `== amount` |
| `is_fully_settled` | `False` | `False` | `True` | `False` |

Because the operation is **not one-shot**, settlement is driven by the standalone **pay** action — payments can be made in multiple partial installments up to `amount_remaining_to_settle`, each guarded by `check_balance_on_payment=True`.

---

## 5. Actions

### 5.1 `create`

Entry points: model `ExpenseOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx only — no payment, not one-shot).

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source is Project | `source.is_project` | `ValidationError` | `"Expense source must be a Project entity."` | `clean_source` | `ExpenseCreateTest.test_source_must_be_a_project_entity` |
| VC2 | Destination is World | `destination.is_world` | `ValidationError` | `"Expense destination must be the World entity."` | `clean_destination` | `ExpenseCreateTest.test_destination_must_be_world_entity` · `test_destination_person_entity_raises_validation_error` |
| VC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | `Operation.clean()` | `ExpenseCreateTest.test_source_must_be_active` |
| VC4 | Destination entity active | `destination.active` | `ValidationError` | same as VC3 | `Operation.clean()` | structural (world is always active) |
| VC5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | `SourceFundMixin` | `ExpenseCreateTest.test_source_fund_must_be_active` |
| VC6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | `TargetFundMixin` | structural (world is always active) |
| VC7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | `ExpenseCreateTest.test_amount_zero_raises_validation_error` · `test_amount_negative_raises_validation_error` |
| VC8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | `OfficerMixin` | `ExpenseCreateTest.test_officer_user_must_be_staff` |
| VC9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | `OfficerMixin` | `ExpenseCreateTest.test_officer_must_be_active` |
| VC10 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | `Operation.clean()` | shared period suite (`OperationPeriodAssignmentTest.test_operation_in_closed_period_raises`) |
| VC11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | `Operation.save()` | shared period suite (`OperationPeriodAssignmentTest.test_operation_raises_when_no_open_period`) |
| VC12 | Issuance balance exempt | no balance check on create (not one-shot; no payment at save) | never fails | — | `_is_one_shot_operation=False`; issuance is non-cash | structural (see `test_project_fund_balance_unchanged_after_save`) |
| VC13 | Category required | `category_id` set | `ValidationError` | `"Category is required for this operation."` | `Operation.clean()` | `ExpenseCreateTest.test_category_required_missing_category_raises` |
| VC14 | Category type is `EXPENSE` | `category.category_type == "EXPENSE"` | `ValidationError` | `"Category '%(category)s' is not a valid EXPENSE category…"` | `Operation.clean()` | `ExpenseCreateTest.test_category_must_be_expense_type` · `test_non_expense_category_type_is_distinct_from_expense` |
| VC15 | Tx entity-type contract | `source.is_project` and `target.is_world` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | `Transaction.create()` | implied by VC1/VC2 (model clean blocks first) |
| VC16 | Tx operation-type allowed | document is `EXPENSE` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | `Transaction.create()` | implied by VC1/VC2 |
| VC17 | Source ≠ target | project ≠ world | always true | `"Source and target funds must be different."` | `Transaction.clean()` | structural (project ≠ world) |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | 1 × `EXPENSE_ISSUANCE`, amount `== op.amount`, `project → world` | `LinkedIssuanceTransactionMixin.save()` | `ExpenseCreateTest.test_save_creates_exactly_one_issuance_transaction` |
| SC2 | No payment on save | no `EXPENSE_PAYMENT` tx at save (not one-shot) | `_is_one_shot_operation=False` | `ExpenseCreateTest.test_no_payment_transaction_created_on_save` |
| SC3 | Tx amount equals op amount | issuance tx `amount == op.amount` | transaction creation | `ExpenseCreateTest.test_issuance_transaction_amount_matches_operation` |
| SC4 | Tx fund direction | issuance tx `source=project`, `target=world` | | `ExpenseCreateTest.test_issuance_transaction_direction_is_project_to_world` |
| SC5 | Non-cash issuance | project fund balance unchanged after save | issuance not a payment type (`payment_types()`) | `ExpenseCreateTest.test_project_fund_balance_unchanged_after_save` |
| SC6 | Remaining == full amount | `amount_remaining_to_settle == amount` after create | `LinkedPaymentTransactionMixin` | `ExpenseCreateTest.test_amount_remaining_to_settle_equals_full_amount_after_creation` |
| SC7 | Not fully settled | `is_fully_settled == False` after create | `amount_settled == 0` | `ExpenseCreateTest.test_is_not_fully_settled_after_creation` |
| SC8 | Project payables ▲ amount | `project.payables == amount` after create | `Entity.payables` | `ExpenseCreateTest.test_create_project_payables_increase` |
| SC9 | Project receivables unchanged | `project.receivables == 0.00` | `Entity.receivables` | `ExpenseCreateTest.test_create_project_receivables_unchanged` |
| SC10 | Category stored on operation | `op.category == selected` after save | `category` FK + `Operation.clean()` | `ExpenseCreateTest.test_expense_category_is_stored_on_operation` |
| SC11 | No invoice / no movements | `has_invoice=False`; no invoice items; no movement lines | `has_invoice=False` | structural (covered by config flag) |
| SC12 | Period auto-assigned | `period` = the project's covering period (open period auto-created at entity creation) | `Operation.save()` + `Entity.save()` | shared period suite (`OperationPeriodAssignmentTest`) |

### 5.2 `pay`

Entry points: model `op.create_payment_transaction(amount, officer, date)` or view `record_transaction_payment` (`POST payment/<pk>/create`). Payment is a cash movement `project.fund → world.fund` that reduces the project payables.

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VP1 | Balance enforced per payment | project fund balance ≥ payment amount | `ValidationError` | `"Insufficient balance…"` | `LinkedPaymentTransactionMixin.create_payment_transaction()` (`check_balance_on_payment=True`) | `ExpensePaymentTest.test_payment_blocked_when_project_fund_has_insufficient_balance` · `test_check_balance_on_payment_is_enabled` |
| VP2 | Amount > 0 | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | `ExpensePaymentTest.test_zero_payment_raises_validation_error` · `test_negative_payment_raises_validation_error` |
| VP3 | Amount ≤ remaining (over-payment guard) | `amount ≤ amount_remaining_to_settle` | `ValidationError` | over-payment rejected | `LinkedPaymentTransactionMixin` | `ExpensePaymentTest.test_payment_exceeding_operation_amount_raises_validation_error` · `test_partial_payment_then_over_payment_raises_validation_error` |
| VP4 | Partial allowed | multiple payments accumulate | — | — | `is_partially_payable=True`, `max_payment_transaction_count=-1` | `ExpensePaymentTest.test_multiple_partial_payments_are_allowed` |
| VP5 | Tx entity/op-type contract | `source.is_project`, `target.is_world`, document is `EXPENSE` | `ValidationError` | tx-type guards | `Transaction.create()` + maps / | implied by model clean |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SP1 | Payment tx created | 1 × `EXPENSE_PAYMENT`, `project → world` | `create_payment_transaction` | `ExpensePaymentTest.test_payment_creates_expense_payment_transaction` |
| SP2 | Tx direction | `source=project`, `target=world` | | `ExpensePaymentTest.test_payment_transaction_direction_is_project_to_world` |
| SP3 | Project fund ▼ amount | `project.balance` decreases by payment amount | `Entity.balance_at` | `ExpensePaymentTest.test_project_fund_decreases_by_payment_amount` |
| SP4 | Remaining ▼ | `amount_remaining_to_settle` decreases by payment | `amount_settled` | `ExpensePaymentTest.test_amount_remaining_to_settle_decreases_after_payment` |
| SP5 | Settled ▲ | `amount_settled` accumulates | `amount_settled` | `ExpensePaymentTest.test_multiple_payments_accumulate_correctly` |
| SP6 | Fully settled at full payment | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | `LinkedPaymentTransactionMixin` | `ExpensePaymentTest.test_full_payment_marks_operation_as_fully_settled` |
| SP7 | Tx count = issuance + payments | 1 issuance + N payments | transaction creation | `ExpensePaymentTest.test_total_transactions_after_partial_payment_is_two` |

### 5.3 `adjust`

Entry points: model `Adjustment` (shared engine for PURCHASE/SALE/EXPENSE) or view `record_accounting_adjustment` (`POST <pk>/adjustment-create`). Adjustments are **non-cash** and change `effective_amount` and the project payables.

#### 5.3.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VA1 | Operation is adjustable | `operation_type` in {PURCHASE, SALE, EXPENSE} | `ValidationError` | non-adjustable op rejected | `Adjustment.clean()` | `AdjustmentValidationTest.test_non_adjustable_operation_type_raises_validation_error` (EXPENSE adjustable via `AdjustmentTransactionTest.test_expense_adjustment_creates_expense_adjustment_transaction`) |
| VA2 | General types require a reason | `reason` set for GENERAL_* types | `ValidationError` | missing reason rejected | `Adjustment.clean()` | `AdjustmentValidationTest.test_general_reduction_without_reason_raises_validation_error` · `test_general_increase_without_reason_raises_validation_error` · `test_general_reduction_with_reason_saves_ok` · `test_non_general_type_without_reason_saves_ok` |
| VA3 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | `AdjustmentValidationTest.test_amount_zero_raises_validation_error` · `test_amount_negative_raises_validation_error` |
| VA4 | Officer staff + active | `officer.is_staff` and `officer.is_active` | `ValidationError` | officer guards | `OfficerMixin` | `AdjustmentValidationTest.test_officer_user_must_be_staff` · `test_officer_must_be_active` |
| VA5 | Not reversed / not a reversal | `reversed_by is None` and `reversal_of is None` | `ValidationError` | reversal guards | `ReversableModel` | `AdjustmentReversalTest.test_cannot_reverse_already_reversed_adjustment` · `test_cannot_reverse_a_reversal` |
| VA6 | Immutability | `operation`/`type`/`amount` unchanged after save | `ValidationError` | `ImmutableMixin` | `ImmutableMixin` | `AdjustmentImmutabilityTest.test_operation_is_immutable_after_save` · `test_type_is_immutable_after_save` · `test_amount_is_immutable_after_save` |

#### 5.3.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SA1 | Adjustment tx created | `EXPENSE_ADJUSTMENT_INCREASE` / `EXPENSE_ADJUSTMENT_DECREASE` (non-cash) | `Adjustment` + maps / | `AdjustmentTransactionTest.test_expense_adjustment_creates_expense_adjustment_transaction` |
| SA2 | Direction per type | increase `project → world`; decrease `world → project` | / | `AdjustmentDirectionTest` (shared direction suite) |
| SA3 | `effective_amount` delta | ▲ for increase, ▼ for decrease, excluding reversed adjustments | `AdjustableMixin` | `AdjustmentEffectiveAmountTest.test_single_decrease_reduces_effective_amount` · `test_single_increase_raises_effective_amount` · `test_mixed_adjustments_combine_correctly` · `test_reversed_adjustment_excluded_from_effective_amount` |
| SA4 | Payables follow adjustment | decrease reduces project payables; reversed adjustment restores | `Entity.payables` | `AdjustmentReversalTest.test_purchase_return_reduces_project_payables` · `test_reverse_adjustment_restores_project_payables` (shared engine) |

### 5.4 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.4.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | `ReversableModel._validate_can_be_reversed` + view guard | `ExpenseReversalTest.test_cannot_reverse_already_reversed_operation` |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | `ReversableModel._validate_can_be_reversed` + view guard | `ExpenseReversalTest.test_cannot_reverse_a_reversal` |
| VR3 | No non-reversed payment txs | no `EXPENSE_PAYMENT` exists (payments are explicit, not implicit) | `ValidationError` | `"You can't reverse this object as it has non-reversed transactions…"` | `ReversableModel._requires_transaction_reversal` + `Operation._implicit_reversable_transaction_types` | `ExpenseReversalTest.test_reversal_blocked_when_payment_exists` |
| VR4 | No non-reversed adjustments | no active adjustments on the operation | `ValidationError` | adjustment guard on reverse | `Operation.reverse()` | shared engine (implied — no dedicated expense test) |
| VR5 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | `operation_reverse_view` | view contract (see §8) |

#### 5.4.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | `ReversableModel.reverse()` | `ExpenseReversalTest.test_reverse_creates_reversal_operation` |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | `ReversableModel.reverse()` | `ExpenseReversalTest.test_reverse_marks_original_as_reversed` |
| SR3 | Reversal marked `is_reversal` | `reversal.is_reversal`, not `is_reversed` | `ReversableModel.reverse()` | `ExpenseReversalTest.test_reversal_is_marked_as_reversal` |
| SR4 | Reversal inherits identity | `amount`, `source`, `destination` copied | `ReversableModel._get_reverse_kwargs` | `ExpenseReversalTest.test_reverse_inherits_amount_source_destination` |
| SR5 | Counter-tx for issuance only | 1 counter-`EXPENSE_ISSUANCE` (payments block reversal; issuance is the only implicit tx) | `Operation._implicit_reversable_transaction_types` + `Transaction.reverse()` | `ExpenseReversalTest.test_reverse_creates_counter_transaction_for_issuance` |
| SR6 | Counter-tx flips funds | counter: `world → project`, same amount, `reversal_of=original` | `Transaction.reverse()` | `ExpenseReversalTest.test_reverse_counter_transaction_flips_funds` |
| SR7 | Project fund unchanged after reversal | issuance is non-cash → no balance change | `balance_at` | `ExpenseReversalTest.test_project_fund_unchanged_after_reversal` |
| SR8 | Payables restored | `project.payables` back to `0.00` | `Entity.payables` | `ExpenseReversalTest.test_reverse_restores_project_payables` |
| SR9 | Receivables unchanged | `project.receivables == 0.00` after reversal | `Entity.receivables` | `ExpenseReversalTest.test_reverse_project_receivables_unchanged` |
| SR10 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger) | whole engine | `ExpenseReversalTest.test_create_then_reverse_leaves_world_unchanged` |

### 5.5 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by `ImmutableMixin` via `_immutable_fields`.

| Branch | Enforced by | Pinned by test |
|--------|-------------|----------------|
| `source` changed after save | `ImmutableMixin.save()` | `ExpenseCreateTest.test_source_is_immutable_after_save` |
| `destination` changed after save | `ImmutableMixin.save()` | `ExpenseCreateTest.test_destination_is_immutable_after_save` |
| `amount` changed after save | `ImmutableMixin.save()` | `ExpenseCreateTest.test_amount_is_immutable_after_save` |

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — `Entity.save()`.
- The operation's governing entity (`period_entity`) is the **source project** (`_source_role = "url"`) — `Operation.period_entity`.
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC11).
- New operations dated inside a **closed** period are rejected (VC10) — `is_date_in_closed_period`.
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period (`_reverse_period`).

---

## 7. Entity roles & balance contract

- Project is the only allowed source; world the only allowed destination — enforced at model (VC1/VC2) and transaction (VC15) layers.
- `project.payables` is derived from **issuance + adjustment-increase** minus **payment + adjustment-decrease** transactions; only `EXPENSE_PAYMENT` moves the project fund balance.
- World is **virtual**: `can_pay` always returns `True`, so the destination never blocks and is never balance-checked (VC12/VP1 apply to the **project** payer).
- The issuance is intentionally **unguarded**: recording the obligation must succeed even with insufficient balance; the actual cash outflow is guarded per payment (VP1).

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Create route | `POST/GET /<project_pk>/expense/create` → `OperationCreateView` |
| Source selection | the **Project** from the URL (`_source_role="url"`); no picker |
| Destination selection | the single **World** entity (`_dest_role="world"`, auto) — no secondary-entity field |
| Category | **required** dropdown filtered to `category_type="EXPENSE"`; passed as `category_id` into `Operation.create()`; enforced again at model (VC13/VC14) |
| Amount | raw `amount` POST field (`_compute_amount`); validated > 0 at model |
| POST parsing | `OperationDataValidator` — date format, description, category, `amount_paid` |
| Pay | `POST payment/<pk>/create` → `record_transaction_payment` — partial or full payment; per-payment balance guard |
| Adjust | `POST <pk>/adjustment-create` → `record_accounting_adjustment` — accounting adjustment (increase/decrease) |
| List entry | "Expense Issuance" link |
| Detail | `operation_detail_view` — shows category, transactions, settlement (paid/remaining), pay + reversal actions |
| Reverse | `operation_reverse_view` — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source=project · VC2 dest=world · VC3 source active · VC4 dest active · VC5 source fund active · VC6 target fund active · VC7 amount>0 · VC8 officer staff · VC9 officer active · VC10 not closed-period · VC11 covering period exists · VC12 issuance balance exempt · VC13 category required · VC14 category type=EXPENSE · VC15 tx entity-type · VC16 tx op-type · VC17 source≠target

**create — effects:** SC1 issuance tx · SC2 no payment on save · SC3 amounts equal · SC4 direction project→world · SC5 non-cash (fund unchanged) · SC6 remaining == amount · SC7 not fully settled · SC8 payables ▲ · SC9 receivables unchanged · SC10 category stored · SC11 no invoice/movements · SC12 period assigned

**pay — validation:** VP1 balance per payment · VP2 amount>0 · VP3 amount ≤ remaining (over-payment guard) · VP4 partial allowed · VP5 tx entity/op-type

**pay — effects:** SP1 payment tx · SP2 direction project→world · SP3 project fund ▼ · SP4 remaining ▼ · SP5 settled ▲ · SP6 fully settled · SP7 tx count issuance+payments

**adjust — validation:** VA1 op adjustable · VA2 general types need reason · VA3 amount>0 · VA4 officer staff+active · VA5 not reversed / not a reversal · VA6 immutability

**adjust — effects:** SA1 adjustment tx · SA2 direction per type · SA3 effective_amount delta · SA4 payables follow adjustment

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no payments · VR4 no non-reversed adjustments · VR5 reason required (view)

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 is_reversal · SR4 identity copied · SR5 counter-tx for issuance only · SR6 counter-tx flips funds · SR7 fund unchanged · SR8 payables restored · SR9 receivables unchanged · SR10 differential invariant

**pay / immutability:** IM1/IM2/IM3 source/destination/amount immutable

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| Tx creation + counts | `ExpenseCreateTest.test_save_creates_exactly_one_issuance_transaction` | SC1 |
| No payment on save | `ExpenseCreateTest.test_no_payment_transaction_created_on_save` | SC2 |
| Tx amount | `ExpenseCreateTest.test_issuance_transaction_amount_matches_operation` | SC3 |
| Tx direction | `ExpenseCreateTest.test_issuance_transaction_direction_is_project_to_world` | SC4 |
| Non-cash issuance | `ExpenseCreateTest.test_project_fund_balance_unchanged_after_save` | SC5, VC12 |
| Settlement after create | `ExpenseCreateTest.test_amount_remaining_to_settle_equals_full_amount_after_creation` · `test_is_not_fully_settled_after_creation` | SC6, SC7 |
| Payables/receivables | `ExpenseCreateTest.test_create_project_payables_increase` · `test_create_project_receivables_unchanged` | SC8, SC9 |
| Category config | `ExpenseCreateTest.test_has_category_config_is_true` · `test_category_required_config_is_true` | config |
| Category creation/type | `ExpenseCreateTest.test_expense_category_can_be_created_with_expense_type` · `test_non_expense_category_type_is_distinct_from_expense` | config |
| Category required | `ExpenseCreateTest.test_category_required_missing_category_raises` | VC13 |
| Category type enforced | `ExpenseCreateTest.test_category_must_be_expense_type` | VC14 |
| Category stored | `ExpenseCreateTest.test_expense_category_is_stored_on_operation` | SC10 |
| Non-category op unaffected | `ExpenseCreateTest.test_non_category_operation_does_not_require_category` | VC13 (negative) |
| Source/dest validation | `ExpenseCreateTest.test_source_must_be_a_project_entity` · `test_destination_must_be_world_entity` · `test_destination_person_entity_raises_validation_error` | VC1, VC2 |
| Active entities/funds | `ExpenseCreateTest.test_source_must_be_active` · `test_source_fund_must_be_active` | VC3, VC5 |
| Amount | `ExpenseCreateTest.test_amount_zero_raises_validation_error` · `test_amount_negative_raises_validation_error` | VC7 |
| Officer | `ExpenseCreateTest.test_officer_user_must_be_staff` · `test_officer_must_be_active` | VC8, VC9 |
| Immutability | `ExpenseCreateTest.test_source_is_immutable_after_save` · `test_destination_is_immutable_after_save` · `test_amount_is_immutable_after_save` | IM1–IM3 |
| Payment tx | `ExpensePaymentTest.test_payment_creates_expense_payment_transaction` · `test_payment_transaction_direction_is_project_to_world` | SP1, SP2 |
| Remaining/settled | `ExpensePaymentTest.test_amount_remaining_to_settle_decreases_after_payment` · `test_multiple_payments_accumulate_correctly` | SP4, SP5 |
| Partial payments | `ExpensePaymentTest.test_multiple_partial_payments_are_allowed` | VP4 |
| Full payment | `ExpensePaymentTest.test_full_payment_marks_operation_as_fully_settled` | SP6 |
| Fund movement | `ExpensePaymentTest.test_project_fund_decreases_by_payment_amount` | SP3 |
| Tx count | `ExpensePaymentTest.test_total_transactions_after_partial_payment_is_two` | SP7 |
| Over-payment guard | `ExpensePaymentTest.test_payment_exceeding_operation_amount_raises_validation_error` · `test_partial_payment_then_over_payment_raises_validation_error` | VP3 |
| Zero/negative payment | `ExpensePaymentTest.test_zero_payment_raises_validation_error` · `test_negative_payment_raises_validation_error` | VP2 |
| Balance guard | `ExpensePaymentTest.test_payment_blocked_when_project_fund_has_insufficient_balance` · `test_check_balance_on_payment_is_enabled` | VP1 |
| Reverse happy path | `ExpenseReversalTest.test_reverse_creates_reversal_operation` · `test_reverse_marks_original_as_reversed` · `test_reversal_is_marked_as_reversal` · `test_reverse_inherits_amount_source_destination` | SR1–SR4 |
| Counter-tx for issuance only | `ExpenseReversalTest.test_reverse_creates_counter_transaction_for_issuance` | SR5 |
| Counter-tx flips funds | `ExpenseReversalTest.test_reverse_counter_transaction_flips_funds` | SR6 |
| Fund unchanged after reverse | `ExpenseReversalTest.test_project_fund_unchanged_after_reversal` | SR7 |
| Payables restored | `ExpenseReversalTest.test_reverse_restores_project_payables` · `test_reverse_project_receivables_unchanged` | SR8, SR9 |
| Differential invariant | `ExpenseReversalTest.test_create_then_reverse_leaves_world_unchanged` | SR10 |
| Reverse blocked by payment | `ExpenseReversalTest.test_reversal_blocked_when_payment_exists` | VR3 |
| Reverse constraints | `ExpenseReversalTest.test_cannot_reverse_already_reversed_operation` · `test_cannot_reverse_a_reversal` | VR1, VR2 |
| Adjust tx | `AdjustmentTransactionTest.test_expense_adjustment_creates_expense_adjustment_transaction` | SA1, VA1 |
| Adjust validation | `AdjustmentValidationTest.test_non_adjustable_operation_type_raises_validation_error` · `test_general_reduction_without_reason_raises_validation_error` · `test_general_increase_without_reason_raises_validation_error` · `test_general_reduction_with_reason_saves_ok` · `test_non_general_type_without_reason_saves_ok` | VA1, VA2 |
| Adjust amount/officer | `AdjustmentValidationTest.test_amount_zero_raises_validation_error` · `test_amount_negative_raises_validation_error` · `test_officer_user_must_be_staff` · `test_officer_must_be_active` | VA3, VA4 |
| Adjust direction | `AdjustmentDirectionTest` | SA2 |
| Effective amount | `AdjustmentEffectiveAmountTest.test_single_decrease_reduces_effective_amount` · `test_single_increase_raises_effective_amount` · `test_mixed_adjustments_combine_correctly` · `test_reversed_adjustment_excluded_from_effective_amount` | SA3 |
| Adjust immutability | `AdjustmentImmutabilityTest.test_operation_is_immutable_after_save` · `test_type_is_immutable_after_save` · `test_amount_is_immutable_after_save` | VA6 |

