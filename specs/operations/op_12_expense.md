# Expense — Operation Contract

**Epic:** 11.3 — Payable Operations
**Type:** Multi-stage, partially payable, category-required
**Actions:** `create`, `pay`, `adjust`, `reverse`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Expense** operation.
> Every clause below is registered to its implementing code (model → mixin → transaction → view) and to its pinning test.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> Other operations follow the same structure — see [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md) and
> [`op_1_cash_injection.md`](op_1_cash_injection.md) for a fully worked example.

**Concept:** Records an obligation to pay for a service or product purchased from an unregistered (world) vendor. The expense carries a `FinancialCategory` (type `EXPENSE`) so it can be filtered/grouped later. The destination is always the **World** entity and the issuance is **unguarded** — the project payables increase by the issuance amount, and only the individual payments are balance-guarded.

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.EXPENSE` (`"EXPENSE"`) | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:15) |
| Proxy class | `ExpenseOperation` | [`op_expense.py`](../../apps/app_operation/models/proxies/op_expense.py:7) |
| URL slug | `"expense"` | [`op_expense.py`](../../apps/app_operation/models/proxies/op_expense.py:11) |
| Label | `"Expense Issuance"` | [`op_expense.py`](../../apps/app_operation/models/proxies/op_expense.py:12) |
| Theme | n/a (not defined on the proxy) | — |
| Source role | `url` (must be a Project) | [`op_expense.py`](../../apps/app_operation/models/proxies/op_expense.py:13) |
| Destination role | `world` | [`op_expense.py`](../../apps/app_operation/models/proxies/op_expense.py:14) |
| Registered in | `PROXY_MAP` | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:37) |
| Cross-op reference | row EX | [`operations-comparison.md`](operations-comparison.md) |

**Configuration flags** (all on [`op_expense.py`](../../apps/app_operation/models/proxies/op_expense.py:7)):

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

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row links the clause to the code that must honor it.

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_source`/`clean_destination` | [`op_expense.py`](../../apps/app_operation/models/proxies/op_expense.py:7) |
| Proxy registry / URL→class resolution | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:37) |
| Shared `Operation` engine (`clean`, `save`, `create`, `reverse`, `resolve_request`, period assignment, category FK enforcement, reversable tx types) | [`operation.py`](../../apps/app_operation/models/operation.py:34) |
| Operation type enum | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:15) |

### 2.2 Core engine (mixins / base)

| Concern | Implementing code |
|---------|-------------------|
| Immutability of `source`/`destination`/`amount`/`period` | [`ImmutableMixin`](../../apps/app_base/mixins.py:30) + `_immutable_fields` in [`operation.py`](../../apps/app_operation/models/operation.py:51) |
| Amount must be > 0 | [`AmountCleanMixin`](../../apps/app_base/mixins.py:64) |
| Officer must be staff + active | [`OfficerMixin`](../../apps/app_base/mixins.py:80) |
| Source fund exists + active | [`SourceFundMixin`](../../apps/app_base/mixins.py:127) |
| Target fund exists + active | [`TargetFundMixin`](../../apps/app_base/mixins.py:147) |
| Issuance tx creation on save | [`LinkedIssuanceTransactionMixin`](../../apps/app_base/mixins.py:184) |
| Standalone payment + per-payment balance guard + settlement | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:242) |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | [`ReversableModel`](../../apps/app_base/models.py:133) + [`Operation.reverse()`](../../apps/app_operation/models/operation.py:997) |
| Adjustable effective amount | [`AdjustableMixin`](../../apps/app_base/mixins.py:89) |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | [`models.py`](../../apps/app_transaction/models.py:33) |
| `EXPENSE_ISSUANCE` (project → world, non-cash, payables ▲) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:77), entity map [:507](../../apps/app_transaction/transaction_type.py:507), op map [:600](../../apps/app_transaction/transaction_type.py:600) |
| `EXPENSE_PAYMENT` (project → world, cash, payables ▼) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:84), entity map [:508](../../apps/app_transaction/transaction_type.py:508), op map [:601](../../apps/app_transaction/transaction_type.py:601), payment set [:424](../../apps/app_transaction/transaction_type.py:424) |
| `EXPENSE_ADJUSTMENT_INCREASE` (project → world, non-cash, payables ▲) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:91), entity map [:509](../../apps/app_transaction/transaction_type.py:509), op map [:602](../../apps/app_transaction/transaction_type.py:602) |
| `EXPENSE_ADJUSTMENT_DECREASE` (world → project, non-cash, payables ▼) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:100), entity map [:510](../../apps/app_transaction/transaction_type.py:510), op map [:603](../../apps/app_transaction/transaction_type.py:603) |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Project payables = issuance/adjustment-increase txs − payment/adjustment-decrease txs | [`Entity.payables`](../../apps/app_entity/models/__init__.py:675) → [`payables_at`](../../apps/app_entity/models/__init__.py:476) |
| Project receivables (unaffected by Expense) | [`Entity.receivables`](../../apps/app_entity/models/__init__.py:681) → [`receivables_at`](../../apps/app_entity/models/__init__.py:511) |
| World (virtual) never balance-checked | [`Entity.can_pay`](../../apps/app_entity/models/__init__.py:704) |
| Open financial period auto-created on entity creation | [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (generic, resolves URL project source + world destination, category dropdown) | [`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:75) |
| POST parsing/validation (date, description, category, amount) | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) |
| Amount computation (raw POST field — no invoice formset) | [`_compute_amount`](../../apps/app_operation/views/create_operation/base.py:52) |
| Category passed into `Operation.create()` | [`base.py`](../../apps/app_operation/views/create_operation/base.py:249) |
| Standalone pay view | [`record_transaction_payment`](../../apps/app_operation/views/record_transaction.py:17) |
| Adjust view (accounting adjustment for PURCHASE/SALE/EXPENSE) | [`record_accounting_adjustment`](../../apps/app_operation/views/adjustment.py:37) |
| Reverse view (reason required) | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) |
| Detail view (transactions + settlement + reversal button) | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) |
| URL: `/<pk>/<op_type>/create` | [`urls.py`](../../apps/app_operation/urls.py:142) |
| URL: `payment/<pk>/create` (pay) | [`urls.py`](../../apps/app_operation/urls.py:152) |
| URL: `/<pk>/adjustment-create` (adjust) | [`urls.py`](../../apps/app_operation/urls.py:157) |
| URL: `/<pk>/detail/` | [`urls.py`](../../apps/app_operation/urls.py:182) |
| URL: `/<pk>/reverse/` | [`urls.py`](../../apps/app_operation/urls.py:192) |
| Templates | [`generic_form.html`](../../apps/app_operation/templates/app_operation/generic_form.html), [`reverse_form.html`](../../apps/app_operation/templates/app_operation/reverse_form.html), [`operation_detail.html`](../../apps/app_operation/templates/app_operation/operation_detail.html), entry link in [`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html:18) |

### 2.6 Tests

| Concern | Test file |
|---------|-----------|
| Create branches | [`test_expense_expense_create.py`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py) |
| Pay branches | [`test_expense_expense_payment.py`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py) |
| Reverse branches | [`test_expense_expense_reversal.py`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py) |
| Adjust branches (shared Purchase/Sale/Expense engine) | [`apps/app_adjustment/tests/test_adjustment_adjustment_*.py`](../../apps/app_adjustment/tests/) |
| Coverage manifest (executable branch registry) | [`tests/base.py`](../../apps/app_operation/tests/base.py:455) |

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

- **Payment source fund:** `self.source` (project) — [`op_expense.py`](../../apps/app_operation/models/proxies/op_expense.py:37)
- **Payment target fund:** `self.destination` (world) — [`op_expense.py`](../../apps/app_operation/models/proxies/op_expense.py:41)

---

## 4. Settlement model

Derived from [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:242) using **payment-type** transactions (`EXPENSE_PAYMENT`) only:

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
| VC1 | Source is Project | `source.is_project` | `ValidationError` | `"Expense source must be a Project entity."` | [`clean_source`](../../apps/app_operation/models/proxies/op_expense.py:48) | [`test_source_must_be_a_project_entity`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:276) |
| VC2 | Destination is World | `destination.is_world` | `ValidationError` | `"Expense destination must be the World entity."` | [`clean_destination`](../../apps/app_operation/models/proxies/op_expense.py:52) | [`test_destination_must_be_world_entity`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:302), [`test_destination_person_entity_raises_validation_error`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:308) |
| VC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | [`test_source_must_be_active`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:282) |
| VC4 | Destination entity active | `destination.active` | `ValidationError` | same as VC3 | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | structural (world is always active) |
| VC5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | [`SourceFundMixin`](../../apps/app_base/mixins.py:132) | [`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:290) |
| VC6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | [`TargetFundMixin`](../../apps/app_base/mixins.py:152) | structural (world is always active) |
| VC7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | [`AmountCleanMixin`](../../apps/app_base/mixins.py:69) | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:318), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:323) |
| VC8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:81) | [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:332) |
| VC9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:84) | [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:340) |
| VC10 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:541) | shared period suite ([`tests/period/`](../../apps/app_operation/tests/period/)) |
| VC11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) | shared period suite |
| VC12 | Issuance balance exempt | no balance check on create (not one-shot; no payment at save) | never fails | — | `_is_one_shot_operation=False`; issuance is non-cash | [`test_project_fund_balance_unchanged_after_save`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:147) |
| VC13 | Category required | `category_id` set | `ValidationError` | `"Category is required for this operation."` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:560) | [`test_category_required_missing_category_raises`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:227) |
| VC14 | Category type is `EXPENSE` | `category.category_type == "EXPENSE"` | `ValidationError` | `"Category '%(category)s' is not a valid EXPENSE category…"` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:568) | [`test_category_must_be_expense_type`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:233) |
| VC15 | Tx entity-type contract | `source.is_project` and `target.is_world` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | [`Transaction.create()`](../../apps/app_transaction/models.py:144) + map [:507](../../apps/app_transaction/transaction_type.py:507) | implied by VC1/VC2 (model clean blocks first) |
| VC16 | Tx operation-type allowed | document is `EXPENSE` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | [`Transaction.create()`](../../apps/app_transaction/models.py:155) + map [:600](../../apps/app_transaction/transaction_type.py:600) | implied by VC1/VC2 |
| VC17 | Source ≠ target | project ≠ world | always true | `"Source and target funds must be different."` | [`Transaction.clean()`](../../apps/app_transaction/models.py:107) | structural (project ≠ world) |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | 1 × `EXPENSE_ISSUANCE`, amount `== op.amount`, `project → world` | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:222) | [`test_save_creates_exactly_one_issuance_transaction`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:120) |
| SC2 | No payment on save | no `EXPENSE_PAYMENT` tx at save (not one-shot) | `_is_one_shot_operation=False` | [`test_no_payment_transaction_created_on_save`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:126) |
| SC3 | Tx amount equals op amount | issuance tx `amount == op.amount` | transaction creation | [`test_issuance_transaction_amount_matches_operation`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:140) |
| SC4 | Tx fund direction | issuance tx `source=project`, `target=world` | [`op_expense.py`](../../apps/app_operation/models/proxies/op_expense.py:37) | [`test_issuance_transaction_direction_is_project_to_world`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:132) |
| SC5 | Non-cash issuance | project fund balance unchanged after save | issuance not a payment type ([`payment_types()`](../../apps/app_transaction/transaction_type.py:418)) | [`test_project_fund_balance_unchanged_after_save`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:147) |
| SC6 | Remaining == full amount | `amount_remaining_to_settle == amount` after create | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:242) | [`test_amount_remaining_to_settle_equals_full_amount_after_creation`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:157) |
| SC7 | Not fully settled | `is_fully_settled == False` after create | `amount_settled == 0` | [`test_is_not_fully_settled_after_creation`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:163) |
| SC8 | Project payables ▲ amount | `project.payables == amount` after create | [`Entity.payables`](../../apps/app_entity/models/__init__.py:675) | [`test_create_project_payables_increase`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:173) |
| SC9 | Project receivables unchanged | `project.receivables == 0.00` | [`Entity.receivables`](../../apps/app_entity/models/__init__.py:681) | [`test_create_project_receivables_unchanged`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:180) |
| SC10 | Category stored on operation | `op.category == selected` after save | `category` FK + `Operation.clean()` | [`test_expense_category_is_stored_on_operation`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:250) |
| SC11 | No invoice / no movements | `has_invoice=False`; no invoice items; no movement lines | `has_invoice=False` | structural (covered by config flag) |
| SC12 | Period auto-assigned | `period` = the project's covering period (open period auto-created at entity creation) | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) + [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) | shared period suite |

### 5.2 `pay`

Entry points: model `op.create_payment_transaction(amount, officer, date)` or view `record_transaction_payment` (`POST payment/<pk>/create`). Payment is a cash movement `project.fund → world.fund` that reduces the project payables.

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VP1 | Balance enforced per payment | project fund balance ≥ payment amount | `ValidationError` | `"Insufficient balance…"` | [`LinkedPaymentTransactionMixin.create_payment_transaction()`](../../apps/app_base/mixins.py:355) (`check_balance_on_payment=True`) | [`test_check_balance_on_payment_is_enabled`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:208), [`test_payment_blocked_when_project_fund_has_insufficient_balance`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:212) |
| VP2 | Amount > 0 | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | [`AmountCleanMixin`](../../apps/app_base/mixins.py:69) | [`test_zero_payment_raises_validation_error`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:196), [`test_negative_payment_raises_validation_error`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:200) |
| VP3 | Amount ≤ remaining (over-payment guard) | `amount ≤ amount_remaining_to_settle` | `ValidationError` | over-payment rejected | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:242) | [`test_payment_exceeding_operation_amount_raises_validation_error`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:186), [`test_partial_payment_then_over_payment_raises_validation_error`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:190) |
| VP4 | Partial allowed | multiple payments accumulate | — | — | `is_partially_payable=True`, `max_payment_transaction_count=-1` | [`test_multiple_partial_payments_are_allowed`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:141), [`test_multiple_payments_accumulate_correctly`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:152) |
| VP5 | Tx entity/op-type contract | `source.is_project`, `target.is_world`, document is `EXPENSE` | `ValidationError` | tx-type guards | [`Transaction.create()`](../../apps/app_transaction/models.py:144) + maps [:508](../../apps/app_transaction/transaction_type.py:508)/[:601](../../apps/app_transaction/transaction_type.py:601) | implied by model clean |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SP1 | Payment tx created | 1 × `EXPENSE_PAYMENT`, `project → world` | [`create_payment_transaction`](../../apps/app_base/mixins.py:355) | [`test_payment_creates_expense_payment_transaction`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:121) |
| SP2 | Tx direction | `source=project`, `target=world` | [`op_expense.py`](../../apps/app_operation/models/proxies/op_expense.py:37) | [`test_payment_transaction_direction_is_project_to_world`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:129) |
| SP3 | Project fund ▼ amount | `project.balance` decreases by payment amount | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) | [`test_project_fund_decreases_by_payment_amount`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:165) |
| SP4 | Remaining ▼ | `amount_remaining_to_settle` decreases by payment | `amount_settled` | [`test_amount_remaining_to_settle_decreases_after_payment`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:136) |
| SP5 | Settled ▲ | `amount_settled` accumulates | `amount_settled` | [`test_multiple_payments_accumulate_correctly`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:152) |
| SP6 | Fully settled at full payment | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:242) | [`test_full_payment_marks_operation_as_fully_settled`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:159) |
| SP7 | Tx count = issuance + payments | 1 issuance + N payments | transaction creation | [`test_total_transactions_after_partial_payment_is_two`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:176) |

### 5.3 `adjust`

Entry points: model `Adjustment` (shared engine for PURCHASE/SALE/EXPENSE) or view `record_accounting_adjustment` (`POST <pk>/adjustment-create`). Adjustments are **non-cash** and change `effective_amount` and the project payables.

#### 5.3.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VA1 | Operation is adjustable | `operation_type` in {PURCHASE, SALE, EXPENSE} | `ValidationError` | non-adjustable op rejected | [`Adjustment.clean()`](../../apps/app_adjustment/models.py) | [`test_expense_adjustment_creates_expense_adjustment_transaction`](../../apps/app_adjustment/tests/test_adjustment_adjustment_transaction.py:207), [`test_non_adjustable_operation_type_raises_validation_error`](../../apps/app_adjustment/tests/test_adjustment_adjustment_validation.py:202) |
| VA2 | General types require a reason | `reason` set for GENERAL_* types | `ValidationError` | missing reason rejected | [`Adjustment.clean()`](../../apps/app_adjustment/models.py) | [`test_general_reduction_without_reason_raises_validation_error`](../../apps/app_adjustment/tests/test_adjustment_adjustment_validation.py:247), [`test_general_increase_without_reason_raises_validation_error`](../../apps/app_adjustment/tests/test_adjustment_adjustment_validation.py:251) |
| VA3 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | [`AmountCleanMixin`](../../apps/app_base/mixins.py:69) | [`test_amount_zero_raises_validation_error`](../../apps/app_adjustment/tests/test_adjustment_adjustment_validation.py:269), [`test_amount_negative_raises_validation_error`](../../apps/app_adjustment/tests/test_adjustment_adjustment_validation.py:273) |
| VA4 | Officer staff + active | `officer.is_staff` and `officer.is_active` | `ValidationError` | officer guards | [`OfficerMixin`](../../apps/app_base/mixins.py:80) | [`test_officer_user_must_be_staff`](../../apps/app_adjustment/tests/test_adjustment_adjustment_validation.py:281), [`test_officer_must_be_active`](../../apps/app_adjustment/tests/test_adjustment_adjustment_validation.py:288) |
| VA5 | Not reversed / not a reversal | `reversed_by is None` and `reversal_of is None` | `ValidationError` | reversal guards | [`ReversableModel`](../../apps/app_base/models.py:133) | shared adjustment reversal tests ([`test_cannot_reverse_already_reversed_adjustment`](../../apps/app_adjustment/tests/test_adjustment_adjustment_reversal.py:235), [`test_cannot_reverse_a_reversal`](../../apps/app_adjustment/tests/test_adjustment_adjustment_reversal.py:242)) |
| VA6 | Immutability | `operation`/`type`/`amount` unchanged after save | `ValidationError` | `ImmutableMixin` | [`ImmutableMixin`](../../apps/app_base/mixins.py:30) | [`test_operation_is_immutable_after_save`](../../apps/app_adjustment/tests/test_adjustment_adjustment_immutability.py:183), [`test_type_is_immutable_after_save`](../../apps/app_adjustment/tests/test_adjustment_adjustment_immutability.py:192), [`test_amount_is_immutable_after_save`](../../apps/app_adjustment/tests/test_adjustment_adjustment_immutability.py:197) |

#### 5.3.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SA1 | Adjustment tx created | `EXPENSE_ADJUSTMENT_INCREASE` / `EXPENSE_ADJUSTMENT_DECREASE` (non-cash) | [`Adjustment`](../../apps/app_adjustment/models.py) + maps [:509](../../apps/app_transaction/transaction_type.py:509)/[:510](../../apps/app_transaction/transaction_type.py:510) | [`test_expense_adjustment_creates_expense_adjustment_transaction`](../../apps/app_adjustment/tests/test_adjustment_adjustment_transaction.py:207) |
| SA2 | Direction per type | increase `project → world`; decrease `world → project` | entity map [:509](../../apps/app_transaction/transaction_type.py:509)/[:510](../../apps/app_transaction/transaction_type.py:510) | shared direction suite ([`test_purchase_return_reverses_direction`](../../apps/app_adjustment/tests/test_adjustment_adjustment_direction.py:188)) |
| SA3 | `effective_amount` delta | ▲ for increase, ▼ for decrease, excluding reversed adjustments | [`AdjustableMixin`](../../apps/app_base/mixins.py:89) | [`test_single_decrease_reduces_effective_amount`](../../apps/app_adjustment/tests/test_adjustment_adjustment_effective_amount.py:192), [`test_single_increase_raises_effective_amount`](../../apps/app_adjustment/tests/test_adjustment_adjustment_effective_amount.py:198), [`test_mixed_adjustments_combine_correctly`](../../apps/app_adjustment/tests/test_adjustment_adjustment_effective_amount.py:204), [`test_reversed_adjustment_excluded_from_effective_amount`](../../apps/app_adjustment/tests/test_adjustment_adjustment_effective_amount.py:218) |
| SA4 | Payables follow adjustment | decrease reduces project payables; reversed adjustment restores | [`Entity.payables`](../../apps/app_entity/models/__init__.py:675) | shared SE4 suite ([`test_purchase_return_reduces_project_payables`](../../apps/app_adjustment/tests/test_adjustment_adjustment_reversal.py:252), [`test_reverse_adjustment_restores_project_payables`](../../apps/app_adjustment/tests/test_adjustment_adjustment_reversal.py:261)) |

### 5.4 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.4.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:34) | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:234) |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:47) | [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:241) |
| VR3 | No non-reversed payment txs | no `EXPENSE_PAYMENT` exists (payments are explicit, not implicit) | `ValidationError` | `"You can't reverse this object as it has non-reversed transactions…"` | [`ReversableModel._requires_transaction_reversal`](../../apps/app_base/models.py:203) + [`Operation._implicit_reversable_transaction_types`](../../apps/app_operation/models/operation.py:478) | [`test_reversal_blocked_when_payment_exists`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:220) |
| VR4 | No non-reversed adjustments | no active adjustments on the operation | `ValidationError` | adjustment guard on reverse | [`Operation.reverse()`](../../apps/app_operation/models/operation.py:997) | shared engine (implied — no dedicated expense test) |
| VR5 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:82) | view contract (see §8) |

#### 5.4.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:235) | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:119) |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:270) | [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:125) |
| SR3 | Reversal marked `is_reversal` | `reversal.is_reversal`, not `is_reversed` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:270) | [`test_reversal_is_marked_as_reversal`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:132) |
| SR4 | Reversal inherits identity | `amount`, `source`, `destination` copied | [`ReversableModel._get_reverse_kwargs`](../../apps/app_base/models.py:184) | [`test_reverse_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:138) |
| SR5 | Counter-tx for issuance only | 1 counter-`EXPENSE_ISSUANCE` (payments block reversal; issuance is the only implicit tx) | [`Operation._implicit_reversable_transaction_types`](../../apps/app_operation/models/operation.py:478) + [`Transaction.reverse()`](../../apps/app_transaction/models.py:206) | [`test_reverse_creates_counter_transaction_for_issuance`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:145) |
| SR6 | Counter-tx flips funds | counter: `world → project`, same amount, `reversal_of=original` | [`Transaction.reverse()`](../../apps/app_transaction/models.py:206) | [`test_reverse_counter_transaction_flips_funds`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:156) |
| SR7 | Project fund unchanged after reversal | issuance is non-cash → no balance change | `balance_at` | [`test_project_fund_unchanged_after_reversal`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:166) |
| SR8 | Payables restored | `project.payables` back to `0.00` | [`Entity.payables`](../../apps/app_entity/models/__init__.py:675) | [`test_reverse_restores_project_payables`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:180) |
| SR9 | Receivables unchanged | `project.receivables == 0.00` after reversal | [`Entity.receivables`](../../apps/app_entity/models/__init__.py:681) | [`test_reverse_project_receivables_unchanged`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:187) |
| SR10 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger) | whole engine | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:196) |

### 5.5 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by [`ImmutableMixin`](../../apps/app_base/mixins.py:30) via `_immutable_fields` ([`operation.py`](../../apps/app_operation/models/operation.py:51)).

| Branch | Enforced by | Pinned by test |
|--------|-------------|----------------|
| `source` changed after save | `ImmutableMixin.save()` | [`test_source_is_immutable_after_save`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:352) |
| `destination` changed after save | `ImmutableMixin.save()` | [`test_destination_is_immutable_after_save`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:361) |
| `amount` changed after save | `ImmutableMixin.save()` | [`test_amount_is_immutable_after_save`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:371) |

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — [`Entity.save()`](../../apps/app_entity/models/__init__.py:714).
- The operation's governing entity (`period_entity`) is the **source project** (`_source_role = "url"`) — [`Operation.period_entity`](../../apps/app_operation/models/operation.py:491).
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC11).
- New operations dated inside a **closed** period are rejected (VC10) — [`is_date_in_closed_period`](../../apps/app_operation/models/period.py:14).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period ([`_reverse_period`](../../apps/app_operation/models/operation.py:455)).

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
| Create route | `POST/GET /<project_pk>/expense/create` → [`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:75) |
| Source selection | the **Project** from the URL (`_source_role="url"`); no picker |
| Destination selection | the single **World** entity (`_dest_role="world"`, auto) — no secondary-entity field |
| Category | **required** dropdown filtered to `category_type="EXPENSE"` ([`base.py`](../../apps/app_operation/views/create_operation/base.py:340)); passed as `category_id` into `Operation.create()` ([`base.py`](../../apps/app_operation/views/create_operation/base.py:249)); enforced again at model (VC13/VC14) |
| Amount | raw `amount` POST field ([`_compute_amount`](../../apps/app_operation/views/create_operation/base.py:52)); validated > 0 at model |
| POST parsing | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) — date format, description, category, `amount_paid` |
| Pay | `POST payment/<pk>/create` → [`record_transaction_payment`](../../apps/app_operation/views/record_transaction.py:17) — partial or full payment; per-payment balance guard |
| Adjust | `POST <pk>/adjustment-create` → [`record_accounting_adjustment`](../../apps/app_operation/views/adjustment.py:37) — accounting adjustment (increase/decrease) |
| List entry | "Expense Issuance" link in [`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html:18) |
| Detail | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) — shows category, transactions, settlement (paid/remaining), pay + reversal actions |
| Reverse | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

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
| Tx creation + counts | [`test_save_creates_exactly_one_issuance_transaction`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:120) | SC1 |
| No payment on save | [`test_no_payment_transaction_created_on_save`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:126) | SC2 |
| Tx amount | [`test_issuance_transaction_amount_matches_operation`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:140) | SC3 |
| Tx direction | [`test_issuance_transaction_direction_is_project_to_world`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:132) | SC4 |
| Non-cash issuance | [`test_project_fund_balance_unchanged_after_save`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:147) | SC5, VC12 |
| Settlement after create | [`test_amount_remaining_to_settle_equals_full_amount_after_creation`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:157), [`test_is_not_fully_settled_after_creation`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:163) | SC6, SC7 |
| Payables/receivables | [`test_create_project_payables_increase`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:173), [`test_create_project_receivables_unchanged`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:180) | SC8, SC9 |
| Category config | [`test_has_category_config_is_true`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:190), [`test_category_required_config_is_true`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:193) | config |
| Category creation/type | [`test_expense_category_can_be_created_with_expense_type`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:196), [`test_non_expense_category_type_is_distinct_from_expense`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:210) | config |
| Category required | [`test_category_required_missing_category_raises`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:227) | VC13 |
| Category type enforced | [`test_category_must_be_expense_type`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:233) | VC14 |
| Category stored | [`test_expense_category_is_stored_on_operation`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:250) | SC10 |
| Non-category op unaffected | [`test_non_category_operation_does_not_require_category`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:258) | VC13 (negative) |
| Source/dest validation | [`test_source_must_be_a_project_entity`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:276), [`test_destination_must_be_world_entity`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:302), [`test_destination_person_entity_raises_validation_error`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:308) | VC1, VC2 |
| Active entities/funds | [`test_source_must_be_active`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:282), [`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:290) | VC3, VC5 |
| Amount | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:318), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:323) | VC7 |
| Officer | [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:332), [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:340) | VC8, VC9 |
| Immutability | [`test_source_is_immutable_after_save`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:352), [`test_destination_is_immutable_after_save`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:361), [`test_amount_is_immutable_after_save`](../../apps/app_operation/tests/operations/expense/test_expense_expense_create.py:371) | IM1–IM3 |
| Payment tx | [`test_payment_creates_expense_payment_transaction`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:121), [`test_payment_transaction_direction_is_project_to_world`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:129) | SP1, SP2 |
| Remaining/settled | [`test_amount_remaining_to_settle_decreases_after_payment`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:136), [`test_multiple_payments_accumulate_correctly`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:152) | SP4, SP5 |
| Partial payments | [`test_multiple_partial_payments_are_allowed`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:141) | VP4 |
| Full payment | [`test_full_payment_marks_operation_as_fully_settled`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:159) | SP6 |
| Fund movement | [`test_project_fund_decreases_by_payment_amount`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:165) | SP3 |
| Tx count | [`test_total_transactions_after_partial_payment_is_two`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:176) | SP7 |
| Over-payment guard | [`test_payment_exceeding_operation_amount_raises_validation_error`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:186), [`test_partial_payment_then_over_payment_raises_validation_error`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:190) | VP3 |
| Zero/negative payment | [`test_zero_payment_raises_validation_error`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:196), [`test_negative_payment_raises_validation_error`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:200) | VP2 |
| Balance guard | [`test_check_balance_on_payment_is_enabled`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:208), [`test_payment_blocked_when_project_fund_has_insufficient_balance`](../../apps/app_operation/tests/operations/expense/test_expense_expense_payment.py:212) | VP1 |
| Reverse happy path | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:119), [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:125), [`test_reversal_is_marked_as_reversal`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:132), [`test_reverse_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:138) | SR1–SR4 |
| Counter-tx for issuance only | [`test_reverse_creates_counter_transaction_for_issuance`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:145) | SR5 |
| Counter-tx flips funds | [`test_reverse_counter_transaction_flips_funds`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:156) | SR6 |
| Fund unchanged after reverse | [`test_project_fund_unchanged_after_reversal`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:166) | SR7 |
| Payables restored | [`test_reverse_restores_project_payables`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:180), [`test_reverse_project_receivables_unchanged`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:187) | SR8, SR9 |
| Differential invariant | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:196) | SR10 |
| Reverse blocked by payment | [`test_reversal_blocked_when_payment_exists`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:220) | VR3 |
| Reverse constraints | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:234), [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/expense/test_expense_expense_reversal.py:241) | VR1, VR2 |
| Adjust tx | [`test_expense_adjustment_creates_expense_adjustment_transaction`](../../apps/app_adjustment/tests/test_adjustment_adjustment_transaction.py:207) | SA1, VA1 |
| Adjust validation | [`test_non_adjustable_operation_type_raises_validation_error`](../../apps/app_adjustment/tests/test_adjustment_adjustment_validation.py:202), [`test_general_reduction_without_reason_raises_validation_error`](../../apps/app_adjustment/tests/test_adjustment_adjustment_validation.py:247), [`test_general_increase_without_reason_raises_validation_error`](../../apps/app_adjustment/tests/test_adjustment_adjustment_validation.py:251) | VA1, VA2 |
| Adjust amount/officer | [`test_amount_zero_raises_validation_error`](../../apps/app_adjustment/tests/test_adjustment_adjustment_validation.py:269), [`test_officer_must_be_active`](../../apps/app_adjustment/tests/test_adjustment_adjustment_validation.py:288) | VA3, VA4 |
| Adjust direction | [`test_purchase_return_reverses_direction`](../../apps/app_adjustment/tests/test_adjustment_adjustment_direction.py:188) | SA2 |
| Effective amount | [`test_single_decrease_reduces_effective_amount`](../../apps/app_adjustment/tests/test_adjustment_adjustment_effective_amount.py:192), [`test_single_increase_raises_effective_amount`](../../apps/app_adjustment/tests/test_adjustment_adjustment_effective_amount.py:198), [`test_reversed_adjustment_excluded_from_effective_amount`](../../apps/app_adjustment/tests/test_adjustment_adjustment_effective_amount.py:218) | SA3 |
| Adjust immutability | [`test_operation_is_immutable_after_save`](../../apps/app_adjustment/tests/test_adjustment_adjustment_immutability.py:183), [`test_amount_is_immutable_after_save`](../../apps/app_adjustment/tests/test_adjustment_adjustment_immutability.py:197) | VA6 |

---

## 11. Tasks

- [x] Verify save creates exactly one `EXPENSE_ISSUANCE` transaction (not payment — not one-shot)
- [x] Verify no `EXPENSE_PAYMENT` transaction is created on save
- [x] Verify issuance direction: `project.fund → world.fund`
- [x] Verify issuance is non-cash: project fund balance unchanged after save
- [x] Verify `amount_remaining_to_settle` equals full amount after creation
- [x] Verify `is_not_fully_settled` after creation
- [x] Verify project payables increase by the issuance amount; receivables unchanged
- [x] Verify source must be a Project entity (non-project source raises `ValidationError`)
- [x] Verify source must be active; source fund must be active
- [x] Verify destination must be the World entity (non-world destination raises `ValidationError`)
- [x] Verify amount/officer validations (zero, negative, non-staff, inactive)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `has_category=True` and `category_required=True` class-level config
- [x] Verify `FinancialCategory` with type `EXPENSE` can be created for the project entity
- [x] Verify category required at model save (`Operation.clean()`), type must be `EXPENSE`
- [x] Verify payment creates `EXPENSE_PAYMENT` (direction: `project.fund → world.fund`)
- [x] Verify payment decreases `amount_remaining_to_settle`
- [x] Verify multiple partial payments are allowed and accumulate
- [x] Verify full payment marks operation as fully settled
- [x] Verify project fund decreases by payment amount (`EXPENSE_PAYMENT` is cash)
- [x] Verify per-payment balance check (`check_balance_on_payment=True`) blocks insufficient-fund payments
- [x] Verify payment cannot exceed remaining amount (over-payment raises `ValidationError`)
- [x] Verify zero/negative payment raises `ValidationError`
- [x] Verify adjustment creates `EXPENSE_ADJUSTMENT_*` tx; `effective_amount` delta; payables follow
- [x] Reversal: reverses issuance counter-transaction only (payment transactions block reversal)
- [x] Verify reversal creates reversal operation with correct linkage
- [x] Verify reversal marks original as reversed; reversal is `is_reversal`
- [x] Verify reversal inherits amount, source, destination from original
- [x] Verify reversal counter-transaction flips source/target funds; project fund unchanged (non-cash)
- [x] Verify payables restored after reversal; differential invariant
- [x] Verify reversal is blocked when any `EXPENSE_PAYMENT` transaction exists
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [x] Add FK from Operation to FinancialCategory to enforce `category_required` at model save level (migration `0008_operation_category`; enforced in `Operation.clean()`; view passes `category_id` into `Operation.create()`)
- [ ] UI: create form — source=Project (url entity), destination=World (auto), category dropdown (required, type=EXPENSE)
- [ ] UI: detail shows category, amount paid, remaining; "Record Payment" button
