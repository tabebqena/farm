# Capital Loss — Operation Contract

**Epic:** 10.3 — Miscellaneous One-Shot Operations
**Type:** One-shot, auto-settled
**Actions:** `create`, `reverse`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Capital Loss** operation.
> Every clause below is registered to its implementing code (model → mixin → transaction → view) and to its pinning test.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> Other operations follow the same structure — see [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md).
>
> **Purpose.** Capital Loss records a **value write-down** of an asset already owned by the project (e.g. a re-valuation below book value). It is a **non-cash, inventory-value-only** operation: it never moves real money, never drains the project's fund balance, and is **not** a death — the asset stays alive and in inventory.

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.CAPITAL_LOSS` (`"CAPITAL_LOSS"`) | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:17) |
| Proxy class | `CapitalLossOperation` | [`op_capital_loss.py`](../../apps/app_operation/models/proxies/op_capital_loss.py:7) |
| URL slug | `"capital-loss"` | [`op_capital_loss.py`](../../apps/app_operation/models/proxies/op_capital_loss.py:11) |
| Label | `"Capital Loss Issuance"` | [`op_capital_loss.py`](../../apps/app_operation/models/proxies/op_capital_loss.py:12) |
| Theme | `danger` / `bi-box-arrow-up-right` (defaults) | [`operation.py`](../../apps/app_operation/models/operation.py:112) |
| Source role | `url` (a Project) | [`op_capital_loss.py`](../../apps/app_operation/models/proxies/op_capital_loss.py:13) |
| Destination role | `system` | [`op_capital_loss.py`](../../apps/app_operation/models/proxies/op_capital_loss.py:14) |
| Registered in | `PROXY_MAP` | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:41) |
| Cross-op reference | row CL | [`operations-comparison.md`](operations-comparison.md:109) |

**Configuration flags** (all on [`op_capital_loss.py`](../../apps/app_operation/models/proxies/op_capital_loss.py:7)):

| Flag | Value | Meaning |
|------|-------|---------|
| `_issuance_transaction_type` | `CAPITAL_LOSS_ISSUANCE` | issuance tx created on save |
| `_payment_transaction_type` | `CAPITAL_LOSS_PAYMENT` | payment tx created on save (one-shot) |
| `_is_one_shot_operation` | `True` | payment fires at create; no standalone pay action |
| `can_pay` | `False` | `process_payment()` is a no-op |
| `is_partially_payable` | `False` | payment must equal amount (one-shot) |
| `max_payment_transaction_count` | `1` | exactly one payment tx ever |
| `check_balance_on_payment` | `False` | **no fund-balance requirement** — a loss-making project may go further into deficit |
| `has_category` / `category_required` | `False` | no financial category |
| `has_repayment` | `False` | no repayment action |
| `has_invoice` | `True` | links the loss to an existing owned product via an invoice item |
| `creates_assets` / `can_create_movement` | `False` | value-only — **no** `InventoryMovementLine` is created |
| `is_adjustable` / `is_items_adjustable` | `False` | not adjustable |

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row links the clause to the code that must honor it.

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_destination` + `payment_source_fund`/`payment_target_fund` | [`op_capital_loss.py`](../../apps/app_operation/models/proxies/op_capital_loss.py:7) |
| Proxy registry / URL→class resolution | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:41) |
| Shared `Operation` engine (`clean`, `save`, `reverse`, `create`, `resolve_request`, period assignment, reversable tx types, inventory-owner helpers) | [`operation.py`](../../apps/app_operation/models/operation.py:34) |
| Operation type enum | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:17) |

### 2.2 Core engine (mixins / base)

| Concern | Implementing code |
|---------|-------------------|
| Immutability of `source`/`destination`/`amount`/`period` | [`ImmutableMixin`](../../apps/app_base/mixins.py:30) + `_immutable_fields` in [`operation.py`](../../apps/app_operation/models/operation.py:51) |
| Amount must be > 0 | [`AmountCleanMixin`](../../apps/app_base/mixins.py:64) |
| Officer must be staff + active | [`OfficerMixin`](../../apps/app_base/mixins.py:80) |
| Source fund exists + active | [`SourceFundMixin`](../../apps/app_base/mixins.py:127) |
| Target fund exists + active | [`TargetFundMixin`](../../apps/app_base/mixins.py:147) |
| Issuance tx creation on save | [`LinkedIssuanceTransactionMixin`](../../apps/app_base/mixins.py:184) |
| One-shot payment tx creation + settlement (`amount_settled`, `is_fully_settled`) | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:242) |
| One-shot / single-payment guard | [`LinkedPaymentTransactionMixin.create_payment_transaction()`](../../apps/app_base/mixins.py:355) |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | [`ReversableModel`](../../apps/app_base/models.py:133) + [`Operation.reverse()`](../../apps/app_operation/models/operation.py:997) |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | [`models.py`](../../apps/app_transaction/models.py:33) |
| `CAPITAL_LOSS_ISSUANCE` (project → system, issuance) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:184), entity map [:527](../../apps/app_transaction/transaction_type.py:527), op map [:616](../../apps/app_transaction/transaction_type.py:616), issuance set [:466](../../apps/app_transaction/transaction_type.py:466) |
| `CAPITAL_LOSS_PAYMENT` (project → system, **non-cash**) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:191), entity map [:528](../../apps/app_transaction/transaction_type.py:528), op map [:617](../../apps/app_transaction/transaction_type.py:617), **excluded** from payment set [:418](../../apps/app_transaction/transaction_type.py:418) |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Project balance = incoming payment txs − outgoing payment txs (payment-types only) | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) |
| System (virtual) never balance-checked | [`Entity.can_pay`](../../apps/app_entity/models/__init__.py:704) |
| Open financial period auto-created on entity creation | [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) |
| P&L cost — `CAPITAL_LOSS_ISSUANCE` (source = fund) | [`Entity.profit_loss()`](../../apps/app_entity/models/__init__.py:546) |
| Movement-based inventory value includes `capital_delta` (gain/loss) | [`capital_delta()`](../../apps/app_inventory/stock.py:90) + [`movement_state()`](../../apps/app_inventory/stock.py:111) |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Dedicated create view (Product Evaluation) | [`EvaluationCreateView`](../../apps/app_operation/views/create_operation/evaluation.py:61) |
| Evaluation form (product picker, new unit price, ownership-restricted queryset) | [`EvaluationForm`](../../apps/app_operation/views/create_operation/evaluation.py:24) |
| Valuation-delta computation → picks `CapitalGainOperation` / `CapitalLossOperation` | [`EvaluationCreateView.post()`](../../apps/app_operation/views/create_operation/evaluation.py:115) |
| Generic create view (secondary path, list links commented out) | [`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:75) |
| POST parsing/validation | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) |
| Reverse view (reason required) | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) |
| Detail view (transactions + reversal button) | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) |
| URL: `/<pk>/evaluate/<product_pk>/` | [`urls.py`](../../apps/app_operation/urls.py:32) |
| URL: `/<pk>/<op_type>/create` (secondary) | [`urls.py`](../../apps/app_operation/urls.py:143) |
| URL: `/<pk>/reverse/` | [`urls.py`](../../apps/app_operation/urls.py:193) |
| URL: `/<pk>/detail/` | [`urls.py`](../../apps/app_operation/urls.py:183) |
| Templates | [`evaluation_form.html`](../../apps/app_operation/templates/app_operation/evaluation_form.html), [`operation_detail.html`](../../apps/app_operation/templates/app_operation/operation_detail.html); entry button in [`stock_detail.html`](../../apps/app_inventory/templates/app_inventory/stock_detail.html:194); operation-list links commented out in [`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html:69) |

### 2.6 Tests

| Concern | Test file |
|---------|-----------|
| Create branches | [`test_capital_loss_capital_loss_create.py`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py) |
| Reverse branches | [`test_capital_loss_capital_loss_reversal.py`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py) |
| Inventory valuation / status | [`test_product.py`](../../apps/app_inventory/tests/test_product.py) |
| Period valuation (single count) | [`test_period_model.py`](../../apps/app_operation/tests/period/test_period_model.py) |
| Evaluation ownership guard | [`test_evaluation_ownership.py`](../../apps/app_operation/tests/views/test_evaluation_ownership.py) |
| Coverage manifest (executable branch registry) | [`tests/base.py`](../../apps/app_operation/tests/base.py:650) |

---

## 3. Money flow & entities

- **Source (payer):** the **Project** entity in the URL (`is_project=True`, `_source_role="url"`). It must be `active=True` and its fund must be `active=True`; **no fund-balance requirement** applies.
- **Destination (receiver):** the single **System** entity (`is_system=True`, `_dest_role="system"`). Virtual — the loss flows to the accounting system, not to a real-money holder.
- **Transaction flow** (both on create, project → system):

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `CAPITAL_LOSS_ISSUANCE` | `project.fund → system.fund` | none (issuance, not a payment type) |
| 2 | `CAPITAL_LOSS_PAYMENT` | `project.fund → system.fund` | **none** — non-cash bookkeeping: `CAPITAL_LOSS_PAYMENT` is **excluded** from `payment_types()`, so the project's fund balance never changes |

- **Payment source fund:** `self.source` (project) — [`op_capital_loss.py`](../../apps/app_operation/models/proxies/op_capital_loss.py:32)
- **Payment target fund:** `self.destination` (system) — [`op_capital_loss.py`](../../apps/app_operation/models/proxies/op_capital_loss.py:36)

> **No cash flow.** The loss is carried entirely by inventory valuation — [`capital_delta()`](../../apps/app_inventory/stock.py:90) subtracts `quantity × unit_price` for each **active** (non-reversed) `CAPITAL_LOSS` invoice item on the linked product.

---

## 4. Settlement model

Derived from [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:242) using payment-type transactions only:

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

Entry points: model `CapitalLossOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx, then payment tx). Through the UI, the entry point is [`EvaluationCreateView.post()`](../../apps/app_operation/views/create_operation/evaluation.py:115), which computes the valuation delta and calls `Operation.create()` on the proxy.

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source is a non-system project | `source.is_project` (system/world rejected) | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | [`Transaction.create()`](../../apps/app_transaction/models.py:144) + map [:527](../../apps/app_transaction/transaction_type.py:527) | [`test_source_system_entity_raises_validation_error`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:103) |
| VC2 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | [`test_source_project_must_be_active`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:108) |
| VC3 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | [`SourceFundMixin`](../../apps/app_base/mixins.py:139) | [`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:116) |
| VC4 | Destination is System | `destination.is_system` | `ValidationError` | `"Capital Loss destination must be the System entity."` | [`clean_destination`](../../apps/app_operation/models/proxies/op_capital_loss.py:40) | [`test_destination_must_be_system_entity`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:128), [`test_destination_world_entity_raises_validation_error`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:134) |
| VC5 | Destination entity active | `destination.active` | `ValidationError` | same as VC2 | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | structural (System is always active) |
| VC6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | [`TargetFundMixin`](../../apps/app_base/mixins.py:159) | structural (System is always active) |
| VC7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | [`AmountCleanMixin`](../../apps/app_base/mixins.py:69) | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:144), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:149) |
| VC8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:82) | [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:158) |
| VC9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:84) | [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:167) |
| VC10 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:541) | covered by period suite |
| VC11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) | covered by period suite |
| VC12 | **No fund-balance requirement** | no balance check | never fails | — | `check_balance_on_payment=False` | [`test_check_balance_on_payment_is_disabled`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:225), [`test_zero_balance_project_can_record_capital_loss`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:233), [`test_loss_larger_than_balance_is_allowed_non_cash`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:249), [`test_loss_making_project_can_record_further_losses`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:262) |
| VC13 | Tx entity-type contract | `source.is_project` and `target.is_system` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | [`Transaction.create()`](../../apps/app_transaction/models.py:144) + map [:527](../../apps/app_transaction/transaction_type.py:527) | implied by VC1/VC4 (model clean blocks first) |
| VC14 | Tx operation-type allowed | document is `CAPITAL_LOSS` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | [`Transaction.create()`](../../apps/app_transaction/models.py:156) + map [:616](../../apps/app_transaction/transaction_type.py:616) | implied by VC1/VC4 |
| VC15 | Source ≠ target | project ≠ system | always true | `"Source and target funds must be different."` | [`Transaction.clean()`](../../apps/app_transaction/models.py:114) | structural (project ≠ system) |
| VC16 | Product ownership (UI) | product belongs to the evaluated project | `ValidationError` / form rejects | `"Product '…' does not belong to '…' and cannot be evaluated."` | [`EvaluationForm`](../../apps/app_operation/views/create_operation/evaluation.py:46) + [`EvaluationCreateView.post()`](../../apps/app_operation/views/create_operation/evaluation.py:196) + [`Operation.save_inventory()`](../../apps/app_operation/models/operation.py:855) | [`test_evaluation_form_restricts_products_to_owned_entity`](../../apps/app_operation/tests/views/test_evaluation_ownership.py:50), [`test_evaluation_post_rejects_other_project_product`](../../apps/app_operation/tests/views/test_evaluation_ownership.py:62) |
| VC17 | Product status eligible | product not SOLD/DEAD/CONSUMED/REMOVED | `ValidationError` | `"Product '…' has status … and cannot be used in new operations."` | [`Product.validate_active()`](../../apps/app_inventory/models.py:760) + [`Operation.save_inventory()`](../../apps/app_operation/models/operation.py:850) | [`test_evaluation_post_accepts_owned_product_form`](../../apps/app_operation/tests/views/test_evaluation_ownership.py:89) |
| VC18 | Product template compatible | template `accepts_operation("CAPITAL_LOSS")` | `ValidationError` | nature↔operation incompatibility | [`ProductTemplate.accepts_operation()`](../../apps/app_inventory/models.py:161) | structural (allowed for all natures) |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | 1 × `CAPITAL_LOSS_ISSUANCE`, amount `== op.amount`, `project → system` | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:222) | [`test_creates_issuance_and_payment_transactions`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:46) |
| SC2 | Payment tx created | 1 × `CAPITAL_LOSS_PAYMENT`, amount `== op.amount`, `project → system` | [`LinkedPaymentTransactionMixin.save()`](../../apps/app_base/mixins.py:424) | same as SC1 |
| SC3 | Tx amounts equal op amount | both txs `amount == op.amount` | transaction creation | [`test_transaction_amounts_match_operation`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:61) |
| SC4 | Tx fund direction | both txs `source=project`, `target=system` | [`op_capital_loss.py`](../../apps/app_operation/models/proxies/op_capital_loss.py:32) | [`test_transaction_funds_are_correct`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:68) |
| SC5 | Fully settled immediately | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:268) | [`test_is_fully_settled_after_creation`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:76) |
| SC6 | No cash flow — project fund unchanged | `project.balance` unchanged by the loss (even a zero-balance or deficit project) | `CAPITAL_LOSS_PAYMENT ∉ payment_types()` → [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) | [`test_project_fund_unchanged_by_loss_amount`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:84), [`test_zero_balance_project_can_record_capital_loss`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:233), [`test_loss_larger_than_balance_is_allowed_non_cash`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:249), [`test_loss_making_project_can_record_further_losses`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:262) |
| SC7 | Inventory value ▼ | `Product.current_value`/`inventory_value` decreases by the loss (`capital_delta`) | [`capital_delta()`](../../apps/app_inventory/stock.py:90) + [`Product.current_value`](../../apps/app_inventory/models.py:747) | [`test_current_value_subtracts_capital_loss`](../../apps/app_inventory/tests/test_product.py:191), [`test_current_value_gain_and_loss_combined`](../../apps/app_inventory/tests/test_product.py:197), [`test_capital_loss_reflected_once_in_inventory_not_cash`](../../apps/app_operation/tests/period/test_period_model.py:465) |
| SC8 | P&L cost ▼ | `profit_loss()` counts `CAPITAL_LOSS_ISSUANCE` (source=fund) as a cost | [`Entity.profit_loss()`](../../apps/app_entity/models/__init__.py:625) | covered by SC7 period test (same tx drives P&L) |
| SC9 | Value-only ledger | loss is value-only: **no** `InventoryMovementLine` created, quantity untouched | `creates_assets=False`, `can_create_movement=False` ([`operation.py`](../../apps/app_operation/models/operation.py:171)) + [`save_inventory`](../../apps/app_operation/models/operation.py:827) | [`test_capital_loss_is_value_only_no_movement_line`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:281) |
| SC10 | Product status unchanged | linked product stays `ACTIVE` (not SOLD/DEAD/CONSUMED) | `save_inventory` links item only ([`operation.py`](../../apps/app_operation/models/operation.py:865)) | [`test_status_active_after_capital_loss`](../../apps/app_inventory/tests/test_product.py:212) |
| SC11 | No double count | `end_assets` decrease `==` recognized loss (counted once in inventory, once in P&L; never in cash balance) | [`period.end_assets`](../../apps/app_operation/models/period.py:392) | [`test_capital_loss_reflected_once_in_inventory_not_cash`](../../apps/app_operation/tests/period/test_period_model.py:465) |
| SC12 | Period auto-assigned | `period` = the project's covering period (open period auto-created at entity creation) | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) + [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) | covered by period suite |

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:34) | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:137) |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:47) | [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:144) |
| VR3 | No explicit txs to reverse | all txs are implicit (one-shot issuance + payment) | `ValidationError` (would require manual reversal) | `"You can't reverse this object as it has non-reversed transactions…"` | [`ReversableModel._requires_transaction_reversal`](../../apps/app_base/models.py:203) + [`Operation._implicit_reversable_transaction_types`](../../apps/app_operation/models/operation.py:478) | implied by successful reverse ([`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:72)) |
| VR4 | No non-reversed adjustments | n/a — Capital Loss is not adjustable | never fails | — | `is_adjustable=False` | n/a |
| VR5 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:84) | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:235) | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:46) |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:270) | [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:52) |
| SR3 | Reversal inherits identity | `amount`, `source`, `destination` copied; `is_reversal=True`, `is_reversed=False` | [`ReversableModel._get_reverse_kwargs`](../../apps/app_base/models.py:184) | [`test_reversal_is_reversal`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:59), [`test_reverse_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:65) |
| SR4 | Counter-tx for issuance | `system → project`, same amount, same type, `reversal_of=original` | [`Transaction.reverse()`](../../apps/app_transaction/models.py:207) | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:72) |
| SR5 | Counter-tx for payment | `system → project`, same amount, same type, `reversal_of=original` | same as SR4 | [`test_reverse_counter_transactions_flip_funds`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:81) |
| SR6 | Counter-txs preserve type + amount | `counter.type == original.type`, `counter.amount == original.amount` | same as SR4 | [`test_reverse_counter_transactions_preserve_type`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:91) |
| SR7 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:226) | covered by reversal suite (implicit) |
| SR8 | Project fund unchanged after reversal | `project.balance` unchanged (loss is non-cash) | `balance_at` | [`test_project_fund_unchanged_after_reversal`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:98) |
| SR9 | Settlement state cleared | `amount_settled == 0`, `is_fully_settled == False` | `amount_settled` | covered by reversal suite (implicit) |
| SR10 | Reason flows to reversal | `reversal.description` contains the reason | [`ReversableModel.reverse()`](../../apps/app_base/models.py:262) | covered by shared engine |
| SR11 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger) | whole engine | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:114) |
| SR12 | Product status stays ACTIVE through reversal | value write-down is not a status transition; reversal does not mutate the product | `save_inventory` / reversal path | [`test_loss_and_reversal_keep_product_active`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:200) |

### 5.3 `pay` (one-shot guard)

There is **no standalone pay action** for Capital Loss:

| Branch | Behavior | Enforced by | Pinned by test |
|--------|----------|-------------|----------------|
| `process_payment()` called | no-op (returns immediately — `can_pay=False`) | [`process_payment`](../../apps/app_operation/models/operation.py:686) | n/a (covered by `can_pay=False`) |
| `create_payment_transaction()` called after create | `ValidationError` — one-shot allows a single payment only, amount must equal `op.amount` | [`create_payment_transaction`](../../apps/app_base/mixins.py:391) | [`test_one_shot_prevents_second_payment`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:210) |

### 5.4 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by [`ImmutableMixin`](../../apps/app_base/mixins.py:30) via `_immutable_fields` ([`operation.py`](../../apps/app_operation/models/operation.py:51)).

| Branch | Enforced by | Pinned by test |
|--------|-------------|----------------|
| `source` changed after save | `ImmutableMixin.save()` | [`test_source_is_immutable`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:179) |
| `destination` changed after save | `ImmutableMixin.save()` | [`test_destination_is_immutable`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:189) |
| `amount` changed after save | `ImmutableMixin.save()` | [`test_amount_is_immutable`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:198) |

---

## 6. Period & financial-period contract

- Every real (non-system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — [`Entity.save()`](../../apps/app_entity/models/__init__.py:714).
- The operation's governing entity (`period_entity`) is the **source project** (`_source_role = "url"`) — [`Operation.period_entity`](../../apps/app_operation/models/operation.py:491).
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC11).
- New operations dated inside a **closed** period are rejected (VC10).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period ([`_reverse_period`](../../apps/app_operation/models/operation.py:455)).

---

## 7. Entity roles & balance contract

- System is the only allowed destination; the URL Project the only allowed source — enforced at model (VC4) and transaction (VC13) layers.
- `project.balance` is derived exclusively from **payment-type** transactions (`balance_at`); `CAPITAL_LOSS_PAYMENT` is **not** a payment type, so the loss never drains the project's fund balance.
- **No fund-balance requirement** — `check_balance_on_payment=False` means a project with a zero or insufficient balance may still record a capital loss; a loss-making project can go further into deficit (VC12).
- System is **virtual**: `can_pay` always returns `True`.
- Inventory value carries the loss via [`capital_delta()`](../../apps/app_inventory/stock.py:90) (only **non-reversed** capital ops count), so the loss appears exactly once in movement-based valuation — never in the cash balance (SC11).

**Scope (loss types):**
- `CAPITAL_LOSS` records a **value write-down only** — the asset (e.g. an animal) stays alive and in inventory: quantity is unchanged, no `InventoryMovementLine` is created, and product status is not changed to DEAD (SC9/SC10).
- Animal **death** is a separate operation ([`op_18_death.md`](op_18_death.md), `DEATH`), which creates inventory movement lines to move the dead animal out of the project. `CAPITAL_LOSS` must never be used for a death.

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Primary create route | `GET/POST /<project_pk>/evaluate/<product_pk>/` → [`EvaluationCreateView`](../../apps/app_operation/views/create_operation/evaluation.py:61) ([`urls.py`](../../apps/app_operation/urls.py:32)); also `/<pk>/evaluate/` without a product |
| Entry point | **"Record Evaluation"** button on the product's stock detail page ([`stock_detail.html`](../../apps/app_inventory/templates/app_inventory/stock_detail.html:194)), restricted to `ACTIVE` products |
| Form | [`EvaluationForm`](../../apps/app_operation/views/create_operation/evaluation.py:24) — product picker (ownership-restricted to the project's products), `new_unit_price` (`min 0.01`), date, notes |
| Direction selection | computed from `delta = (new_unit_price − current_unit_price) × quantity`: `delta > 0 → CapitalGainOperation`, `delta < 0 → CapitalLossOperation`, `|delta| < 0.01 → no operation` ([`post()`](../../apps/app_operation/views/create_operation/evaluation.py:178)) |
| Source selection | the **Project** from the URL (`_source_role="url"`); no secondary-entity field |
| Destination selection | locked to the single **System** entity (`_dest_role="system"`, resolved by [`resolve_request`](../../apps/app_operation/models/operation.py:202)); no picker |
| Amount | derived from the invoice item (`quantity × |Δ unit price|`) created by the evaluation view |
| Category | hidden (no category) |
| Secondary create route | `/<pk>/<op_type>/create` with `op_type="capital-loss"` exists ([`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:75)), but the operation-list links are **commented out** ([`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html:69)) |
| Detail | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) — shows both transactions + settlement + reversal button |
| Reverse | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source=project (system/world rejected) · VC2 source active · VC3 source fund active · VC4 dest=system · VC5 dest active · VC6 target fund active · VC7 amount>0 · VC8 officer staff · VC9 officer active · VC10 not closed-period · VC11 covering period exists · VC12 no balance requirement · VC13 tx entity-type · VC14 tx op-type · VC15 source≠target · VC16 product ownership · VC17 product status eligible · VC18 template compatible

**create — effects:** SC1 issuance tx · SC2 payment tx · SC3 amounts equal · SC4 direction project→system · SC5 settled immediately · SC6 no cash flow (fund unchanged, even in deficit) · SC7 inventory value ▼ · SC8 P&L cost ▼ · SC9 value-only (no movement line) · SC10 product ACTIVE · SC11 no double count · SC12 period assigned

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no explicit txs · VR4 no adjustments (n/a) · VR5 reason required (view)

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 identity copied · SR4 issuance counter-tx · SR5 payment counter-tx · SR6 type/amount preserved · SR7 reversal owns no txs · SR8 fund unchanged after reversal · SR9 settlement cleared · SR10 reason in description · SR11 differential invariant · SR12 product stays ACTIVE

**pay / immutability:** BP1 `process_payment` no-op · BP2 `create_payment_transaction` blocked after create · IM1/IM2/IM3 source/destination/amount immutable

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| Tx creation + counts | [`test_creates_issuance_and_payment_transactions`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:46) | SC1, SC2 |
| Tx amounts | [`test_transaction_amounts_match_operation`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:61) | SC3 |
| Tx direction | [`test_transaction_funds_are_correct`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:68) | SC4 |
| Settlement | [`test_is_fully_settled_after_creation`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:76) | SC5 |
| Non-cash (fund unchanged) | [`test_project_fund_unchanged_by_loss_amount`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:84) | SC6 |
| Source validation | [`test_source_system_entity_raises_validation_error`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:103) | VC1 |
| Active source + fund | [`test_source_project_must_be_active`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:108), [`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:116) | VC2, VC3 |
| Destination validation | [`test_destination_must_be_system_entity`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:128), [`test_destination_world_entity_raises_validation_error`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:134) | VC4 |
| Amount | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:144), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:149) | VC7 |
| Officer | [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:158), [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:167) | VC8, VC9 |
| Immutability | [`test_source_is_immutable`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:179), [`test_destination_is_immutable`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:189), [`test_amount_is_immutable`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:198) | IM1–IM3 |
| One-shot guard | [`test_one_shot_prevents_second_payment`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:210) | BP2 |
| Balance exempt / deficit allowed | [`test_check_balance_on_payment_is_disabled`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:225), [`test_zero_balance_project_can_record_capital_loss`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:233), [`test_loss_larger_than_balance_is_allowed_non_cash`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:249), [`test_loss_making_project_can_record_further_losses`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:262) | VC12, SC6 |
| Value-only, no movement line | [`test_capital_loss_is_value_only_no_movement_line`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py:281) | SC9 |
| Reverse happy path | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:46), [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:52), [`test_reversal_is_reversal`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:59), [`test_reverse_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:65) | SR1–SR3 |
| Counter txs | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:72), [`test_reverse_counter_transactions_flip_funds`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:81), [`test_reverse_counter_transactions_preserve_type`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:91) | SR4–SR6 |
| Non-cash after reversal | [`test_project_fund_unchanged_after_reversal`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:98) | SR8 |
| Reverse constraints | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:137), [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:144) | VR1, VR2 |
| Differential invariant | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:114) | SR11 |
| Value-only, product ACTIVE (create + reverse) | [`test_loss_and_reversal_keep_product_active`](../../apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py:200) | SC9, SC10, SR12 |
| Inventory valuation (capital_delta) | [`test_current_value_subtracts_capital_loss`](../../apps/app_inventory/tests/test_product.py:191), [`test_current_value_gain_and_loss_combined`](../../apps/app_inventory/tests/test_product.py:197) | SC7 |
| Product status ACTIVE | [`test_status_active_after_capital_loss`](../../apps/app_inventory/tests/test_product.py:212) | SC10 |
| Single-count valuation | [`test_capital_loss_reflected_once_in_inventory_not_cash`](../../apps/app_operation/tests/period/test_period_model.py:465) | SC7, SC11 |
| Evaluation ownership guard | [`test_evaluation_form_restricts_products_to_owned_entity`](../../apps/app_operation/tests/views/test_evaluation_ownership.py:50), [`test_evaluation_post_rejects_other_project_product`](../../apps/app_operation/tests/views/test_evaluation_ownership.py:62), [`test_evaluation_post_accepts_owned_product_form`](../../apps/app_operation/tests/views/test_evaluation_ownership.py:89) | VC16, VC17 |

---

## 11. Tasks

- [x] Verify both `CAPITAL_LOSS_ISSUANCE` and `CAPITAL_LOSS_PAYMENT` are created on save
- [x] Verify transaction fund direction: `project.fund → system.fund` for both
- [x] Verify operation is fully settled immediately
- [x] Verify all validation branches VC1–VC18
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `create_payment_transaction()` is blocked after creation (one-shot)
- [x] Verify reversal creates counter-transactions: `system.fund → project.fund`
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify counter-transactions preserve transaction type
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [x] Verify the loss is **non-cash**: project fund unchanged on create and after reversal, even with a zero/insufficient balance (deficit allowed)
- [x] Verify the loss is value-only: no `InventoryMovementLine`, product stays `ACTIVE` through create + reverse
- [x] Verify the loss is counted **once** in inventory value and **once** in P&L — never in the cash balance (no double count)
- [x] Verify `CAPITAL_LOSS` is a value write-down only — never used for a death (`DEATH` is a separate operation)
- [x] Verify the evaluation UI computes the direction from the valuation delta and enforces product ownership
- [ ] UI: operation detail shows issuance transaction and reversal button (pinned by view coverage)
- [ ] Complete test suite covering all branches; each test has a small number of assertions (one behavior per test)
