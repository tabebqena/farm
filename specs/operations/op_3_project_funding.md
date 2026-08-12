# Project Funding — Operation Contract

**Epic:** 9.1 — Project Capital Operations
**Type:** One-shot, auto-settled
**Actions:** `create`, `reverse`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Project Funding** operation.
> Every clause below is registered to its implementing code (model → mixin → transaction → view) and to its pinning test.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> Other operations follow the same structure — see [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md).

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.PROJECT_FUNDING` (`"PROJECT_FUNDING"`) | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:7) |
| Proxy class | `ProjectFundingOperation` | [`op_project_funding.py`](../../apps/app_operation/models/proxies/op_project_funding.py:8) |
| URL slug | `"project-funding"` | [`op_project_funding.py`](../../apps/app_operation/models/proxies/op_project_funding.py:12) |
| Label | `"Project Funding"` | [`op_project_funding.py`](../../apps/app_operation/models/proxies/op_project_funding.py:13) |
| Theme | `danger` / `bi-box-arrow-up-right` (inherited default — not overridden) | [`operation.py`](../../apps/app_operation/models/operation.py:112) |
| Source role | `url` (must be a Person) | [`op_project_funding.py`](../../apps/app_operation/models/proxies/op_project_funding.py:14) |
| Destination role | `post` (must be a Project, picked from secondary field) | [`op_project_funding.py`](../../apps/app_operation/models/proxies/op_project_funding.py:15) |
| Registered in | `PROXY_MAP` | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:29) |
| Cross-op reference | row PF | [`operations-comparison.md`](operations-comparison.md) |

**Configuration flags** (all on [`op_project_funding.py`](../../apps/app_operation/models/proxies/op_project_funding.py:8)):

| Flag | Value | Meaning |
|------|-------|---------|
| `_issuance_transaction_type` | `PROJECT_FUNDING_ISSUANCE` | issuance tx created on save |
| `_payment_transaction_type` | `PROJECT_FUNDING_PAYMENT` | payment tx created on save (one-shot) |
| `_is_one_shot_operation` | `True` | payment fires at create; no standalone pay action |
| `can_pay` | `False` | `process_payment()` is a no-op |
| `is_partially_payable` | `False` | payment must equal amount (one-shot) |
| `max_payment_transaction_count` | `1` | exactly one payment tx ever |
| `check_balance_on_payment` | `False` (inherited default) | balance enforced by `clean()` at create, not per-payment |
| `has_category` / `category_required` | `False` | no financial category |
| `has_repayment` | `False` | no repayment action |
| `has_invoice` | `False` | no invoice items / no inventory movements |

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row links the clause to the code that must honor it.

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_source`/`clean_destination` + `clean()` (shareholder + balance) | [`op_project_funding.py`](../../apps/app_operation/models/proxies/op_project_funding.py:8) |
| Project picker (`get_related_entities` — projects the URL person is a shareholder of) | [`op_project_funding.py`](../../apps/app_operation/models/proxies/op_project_funding.py:44) |
| Proxy registry / URL→class resolution | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:29) |
| Shared `Operation` engine (`clean`, `save`, `reverse`, `create`, `resolve_request`, period assignment, reversable tx types) | [`operation.py`](../../apps/app_operation/models/operation.py:34) |
| Operation type enum | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:7) |

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
| Payer balance check at create (via `fund.can_pay`) | [`op_project_funding.py:clean()`](../../apps/app_operation/models/proxies/op_project_funding.py:88) |
| One-shot guard (single payment, amount == op.amount) | [`LinkedPaymentTransactionMixin.create_payment_transaction()`](../../apps/app_base/mixins.py:391) |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | [`ReversableModel`](../../apps/app_base/models.py:133) + [`Operation.reverse()`](../../apps/app_operation/models/operation.py:997) |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | [`models.py`](../../apps/app_transaction/models.py:33) |
| `PROJECT_FUNDING_ISSUANCE` (shareholder → project) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:233), entity map [:533](../../apps/app_transaction/transaction_type.py:533), op map [:619](../../apps/app_transaction/transaction_type.py:619) |
| `PROJECT_FUNDING_PAYMENT` (shareholder → project, affects balance) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:240), entity map [:534](../../apps/app_transaction/transaction_type.py:534), op map [:620](../../apps/app_transaction/transaction_type.py:620), payment set [:433](../../apps/app_transaction/transaction_type.py:433) |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Person balance = incoming payment txs − outgoing payment txs | [`Entity.balance`](../../apps/app_entity/models/__init__.py:668) → [`balance_at`](../../apps/app_entity/models/__init__.py:414) |
| Balance enforcement: `can_pay` only balance-checks real (non-virtual) internal funds | [`Entity.can_pay`](../../apps/app_entity/models/__init__.py:704) |
| Role flags `is_person` / `is_project` | [`is_person`](../../apps/app_entity/models/__init__.py:273), [`is_project`](../../apps/app_entity/models/__init__.py:269) |
| Active-shareholder relationship (used by `clean()` + picker) | `Stakeholder` + `StakeholderRole.SHAREHOLDER` (see [`op_project_funding.py`](../../apps/app_operation/models/proxies/op_project_funding.py:76)) |
| Open financial period auto-created on entity creation | [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (generic, resolves URL person source + `post` project destination) | [`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:75) |
| POST parsing/validation | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) |
| Reverse view (reason required) | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) |
| Detail view (transactions + reversal button) | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) |
| URL: `/<pk>/<op_type>/create` | [`urls.py`](../../apps/app_operation/urls.py:142) |
| URL: `/<pk>/reverse/` | [`urls.py`](../../apps/app_operation/urls.py:192) |
| URL: `/<pk>/detail/` | [`urls.py`](../../apps/app_operation/urls.py:182) |
| Templates | [`generic_form.html`](../../apps/app_operation/templates/app_operation/generic_form.html), [`reverse_form.html`](../../apps/app_operation/templates/app_operation/reverse_form.html), [`operation_detail.html`](../../apps/app_operation/templates/app_operation/operation_detail.html), entry link in [`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html:31) |

### 2.6 Tests

| Concern | Test file |
|---------|-----------|
| Create branches | [`test_project_funding_project_funding_create.py`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py) |
| Reverse branches | [`test_project_funding_project_funding_reversal.py`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py) |
| Coverage manifest (executable branch registry) | [`tests/base.py`](../../apps/app_operation/tests/base.py:733) |

---

## 3. Money flow & entities

- **Source (payer):** the **Person** (shareholder/funder) entity in the URL (`is_person=True`). Its fund is the source fund and is **balance-checked at create** (VC12) — the funder's real internal fund must cover `amount`.
- **Destination (receiver):** the **Project** entity selected via the secondary field (`is_project=True`). The funder must be a registered **active shareholder** of that project (VC16).
- **Transaction flow** (both on create, person → project):

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `PROJECT_FUNDING_ISSUANCE` | `person.fund → project.fund` | none (issuance, not a payment type) |
| 2 | `PROJECT_FUNDING_PAYMENT` | `person.fund → project.fund` | ▼ funder person by `amount`; ▲ project by `amount` |

- **Payment source fund:** `self.source` (funder person) — [`op_project_funding.py`](../../apps/app_operation/models/proxies/op_project_funding.py:29)
- **Payment target fund:** `self.destination` (project) — [`op_project_funding.py`](../../apps/app_operation/models/proxies/op_project_funding.py:33)

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

Entry points: model `ProjectFundingOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx, then payment tx).

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source is Person | `source.is_person` | `ValidationError` | `"Project Funding source must be a Person entity."` | [`clean_source`](../../apps/app_operation/models/proxies/op_project_funding.py:59) | [`test_source_must_be_person_entity`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:129) |
| VC2 | Destination is Project | `destination.is_project` | `ValidationError` | `"Project Funding destination must be a Project entity."` | [`clean_destination`](../../apps/app_operation/models/proxies/op_project_funding.py:63) | [`test_destination_must_be_project_entity`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:151) |
| VC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | [`test_source_entity_must_be_active`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:157) |
| VC4 | Destination entity active | `destination.active` | `ValidationError` | same as VC3 | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | [`test_destination_entity_must_be_active`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:165) |
| VC5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | [`SourceFundMixin`](../../apps/app_base/mixins.py:132) | merged with VC3 ([`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:173)) |
| VC6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | [`TargetFundMixin`](../../apps/app_base/mixins.py:152) | merged with VC4 |
| VC7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | [`AmountCleanMixin`](../../apps/app_base/mixins.py:69) | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:185), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:190) |
| VC8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:81) | [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:213) |
| VC9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:84) | [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:221) |
| VC10 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:541) | [`test_operation_blocked_when_destination_in_closed_period`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:320), [`test_operation_blocked_when_source_in_closed_period`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:341) |
| VC11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) | covered by the shared period suite (see §10) |
| VC12 | Balance checked at create (funder pays) | `payment_source_fund.can_pay(amount)` | `ValidationError` | `"Insufficient funds: balance is %(balance)s, cannot fund %(amount)s."` | [`op_project_funding.py:clean()`](../../apps/app_operation/models/proxies/op_project_funding.py:95) → [`Entity.can_pay`](../../apps/app_entity/models/__init__.py:704) | [`test_amount_exceeding_funder_balance_raises_error`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:195), [`test_amount_equal_to_funder_balance_succeeds`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:202), [`test_check_balance_on_payment_is_disabled`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:312) |
| VC13 | Tx entity-type contract | `source.is_person` and `target.is_project` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | [`Transaction.create()`](../../apps/app_transaction/models.py:144) + map [:533](../../apps/app_transaction/transaction_type.py:533) | implied by VC1/VC2 (model clean blocks first) |
| VC14 | Tx operation-type allowed | document is `PROJECT_FUNDING` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | [`Transaction.create()`](../../apps/app_transaction/models.py:155) + map [:619](../../apps/app_transaction/transaction_type.py:619) | implied by VC1/VC2 |
| VC15 | Source ≠ target | person ≠ project | always true | `"Source and target funds must be different."` | [`Transaction.clean()`](../../apps/app_transaction/models.py:107) | structural (person ≠ project) |
| VC16 | Source is active shareholder of destination | an active `StakeholderRole.SHAREHOLDER` link exists from the project to the source | `ValidationError` | `"The funding source must be a registered shareholder of the project."` | [`op_project_funding.py:clean()`](../../apps/app_operation/models/proxies/op_project_funding.py:76) | [`test_source_must_be_shareholder_of_destination_project`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:141) |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | 1 × `PROJECT_FUNDING_ISSUANCE`, amount `== op.amount`, `person → project` | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:222) | [`test_creates_issuance_and_payment_transactions`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:81) |
| SC2 | Payment tx created | 1 × `PROJECT_FUNDING_PAYMENT`, amount `== op.amount`, `person → project` | [`LinkedPaymentTransactionMixin.save()`](../../apps/app_base/mixins.py:424) | same as SC1 |
| SC3 | Tx amounts equal op amount | both txs `amount == op.amount` | transaction creation | [`test_transaction_amounts_match_operation`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:98) |
| SC4 | Tx fund direction | both txs `source=person`, `target=project` | [`op_project_funding.py`](../../apps/app_operation/models/proxies/op_project_funding.py:29) | [`test_transaction_funds_are_correct`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:105) |
| SC5 | Fully settled immediately | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:268) | [`test_is_fully_settled_after_creation`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:117) |
| SC6 | Project fund ▲ amount | `project.balance` increases by `amount` | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) | [`test_project_fund_increases_after_funding`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:286) |
| SC7 | Funder fund ▼ amount | `person.balance` decreases by `amount` | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) | [`test_funder_fund_decreases_after_funding`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:297) |
| SC8 | No invoice / no movements | `has_invoice=False`; no invoice items; no movement lines | `has_invoice=False` | config flag (`has_invoice=False`); no ledger/movement machinery in `post_save_tasks` |
| SC9 | Period auto-assigned | `period` = the funder's covering period (open period auto-created at entity creation) | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) + [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) | covered by shared period suite |

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:34) | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:129) |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:47) | [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:136) |
| VR3 | No explicit txs to reverse | all txs are implicit (one-shot issuance + payment) | `ValidationError` (would require manual reversal) | `"You can't reverse this object as it has non-reversed transactions…"` | [`ReversableModel._requires_transaction_reversal`](../../apps/app_base/models.py:203) + [`Operation._implicit_reversable_transaction_types`](../../apps/app_operation/models/operation.py:478) | implied by successful reverse ([`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:96)) |
| VR4 | No non-reversed adjustments | n/a — Project Funding is not adjustable | never fails | — | `is_adjustable=False` | n/a |
| VR5 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:82) | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:235) | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:70) |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:270) | [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:76) |
| SR3 | Reversal inherits identity | `amount`, `source`, `destination` copied | [`ReversableModel._get_reverse_kwargs`](../../apps/app_base/models.py:184) | [`test_reverse_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:89) |
| SR4 | Counter-tx for issuance | `project → person`, same amount, same type, `reversal_of=original` | [`Transaction.reverse()`](../../apps/app_transaction/models.py:206) | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:96) |
| SR5 | Counter-tx for payment | `project → person`, same amount, same type, `reversal_of=original` | same as SR4 | [`test_reverse_counter_transactions_flip_funds`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:108) |
| SR6 | Counter-txs preserve type + amount | `counter.type == original.type`, `counter.amount == original.amount` | same as SR4 | [`test_reverse_counter_transactions_preserve_type`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:118) |
| SR7 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:226) | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:102) |
| SR8 | Funder + project restored | `person.balance` and `project.balance` back to pre-create baseline | `balance_at` | [`test_funder_fund_restored_after_reversal`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:155), [`test_project_fund_restored_after_reversal`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:146) |
| SR9 | Settlement state cleared | `amount_settled == 0`, `is_fully_settled == False` | `amount_settled` | differential invariant ([`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:168)); no dedicated focused test yet (see §11) |
| SR10 | Reason flows to reversal | `reversal.description` contains the reason | [`ReversableModel.reverse()`](../../apps/app_base/models.py:262) | shared engine (see §11 — no dedicated focused test yet) |
| SR11 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger) | whole engine | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:168) |

### 5.3 `pay` (one-shot guard)

There is **no standalone pay action** for Project Funding:

| Branch | Behavior | Enforced by | Pinned by test |
|--------|----------|-------------|----------------|
| `process_payment()` called | no-op (returns immediately — `can_pay=False`) | [`process_payment`](../../apps/app_operation/models/operation.py:686) | n/a (covered by `can_pay=False`) |
| `create_payment_transaction()` called after create | `ValidationError` — one-shot allows a single payment only, amount must equal `op.amount` (balance re-checked first, VC12) | [`create_payment_transaction`](../../apps/app_base/mixins.py:391) | [`test_one_shot_prevents_second_payment`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:271) |

### 5.4 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by [`ImmutableMixin`](../../apps/app_base/mixins.py:30) via `_immutable_fields` ([`operation.py`](../../apps/app_operation/models/operation.py:51)).

| Branch | Enforced by | Pinned by test |
|--------|-------------|----------------|
| `source` changed after save | `ImmutableMixin.save()` | [`test_source_is_immutable`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:233) |
| `destination` changed after save | `ImmutableMixin.save()` | [`test_destination_is_immutable`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:249) |
| `amount` changed after save | `ImmutableMixin.save()` | [`test_amount_is_immutable`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:259) |

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — [`Entity.save()`](../../apps/app_entity/models/__init__.py:714).
- The operation's governing entity (`period_entity`) is the **source funder person** (`_source_role = "url"`) — [`Operation.period_entity`](../../apps/app_operation/models/operation.py:498).
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC11).
- New operations dated inside a **closed** period are rejected (VC10) — checked for **both** source and destination entities; pinned by the closed-period regression tests (see §10).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period ([`_reverse_period`](../../apps/app_operation/models/operation.py:455)).

---

## 7. Entity roles & balance contract

- Person (shareholder) is the only allowed source; project the only allowed destination — enforced at model (VC1/VC2/VC16) and transaction (VC13) layers.
- The funder must be a registered **active shareholder** of the destination project (VC16) — enforced in `clean()` via the project's `stakeholders` relation.
- `person.balance` / `project.balance` are derived exclusively from **payment-type** transactions (`balance_at`); the issuance tx never moves a balance.
- The funder's fund is a **real internal fund** and is balance-checked at create (`clean()`, VC12). `check_balance_on_payment` stays `False` — the balance is guaranteed once at creation, and the one-shot payment then matches it exactly.

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Create route | `POST/GET /<person_pk>/project-funding/create` → [`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:75) |
| Source selection | the **Person (funder)** from the URL (`_source_role="url"`, resolved by [`resolve_request`](../../apps/app_operation/models/operation.py:202)); no picker |
| Destination selection | a **Project** picked from the secondary field (`_dest_role="post"`); [`get_related_entities`](../../apps/app_operation/models/proxies/op_project_funding.py:44) returns the projects for which the URL person is an active shareholder |
| Category | hidden (no category) |
| Amount | raw `amount` POST field ([`_compute_amount`](../../apps/app_operation/views/create_operation/base.py:52)); validated > 0 at model; balance-checked at create (VC12) |
| POST parsing | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) — date format, description, category (n/a), `amount_paid` (n/a, forced 0) |
| List entry | "Project Funding" link in [`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html:31) |
| Detail | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) — shows both transactions + settlement + reversal button |
| Reverse | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source=person · VC2 dest=project · VC3 source active · VC4 dest active · VC5 source fund active · VC6 target fund active · VC7 amount>0 · VC8 officer staff · VC9 officer active · VC10 not closed-period · VC11 covering period exists · VC12 balance checked (clean) · VC13 tx entity-type · VC14 tx op-type · VC15 source≠target · VC16 source is active shareholder of dest

**create — effects:** SC1 issuance tx · SC2 payment tx · SC3 amounts equal · SC4 direction person→project · SC5 settled immediately · SC6 project ▲ · SC7 funder ▼ · SC8 no invoice/movements · SC9 period assigned

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no explicit txs · VR4 no adjustments (n/a) · VR5 reason required (view)

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 identity copied · SR4 issuance counter-tx · SR5 payment counter-tx · SR6 type/amount preserved · SR7 reversal owns no txs · SR8 funder+project restored · SR9 settlement cleared · SR10 reason in description · SR11 differential invariant

**pay / immutability:** BP1 `process_payment` no-op · BP2 `create_payment_transaction` blocked after create · IM1/IM2/IM3 source/destination/amount immutable

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| Tx creation + counts | [`test_creates_issuance_and_payment_transactions`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:81) | SC1, SC2 |
| Tx amounts | [`test_transaction_amounts_match_operation`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:98) | SC3 |
| Tx direction | [`test_transaction_funds_are_correct`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:105) | SC4 |
| Settlement | [`test_is_fully_settled_after_creation`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:117) | SC5 |
| Source/dest validation | [`test_source_must_be_person_entity`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:129), [`test_destination_must_be_project_entity`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:151) | VC1, VC2 |
| Shareholder check | [`test_source_must_be_shareholder_of_destination_project`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:141) | VC16 |
| Active entities | [`test_source_entity_must_be_active`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:157), [`test_destination_entity_must_be_active`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:165), [`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:173) | VC3–VC6 |
| Amount | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:185), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:190) | VC7 |
| Balance check | [`test_amount_exceeding_funder_balance_raises_error`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:195), [`test_amount_equal_to_funder_balance_succeeds`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:202), [`test_check_balance_on_payment_is_disabled`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:312) | VC12 |
| Officer | [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:213), [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:221) | VC8, VC9 |
| Immutability | [`test_source_is_immutable`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:233), [`test_destination_is_immutable`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:249), [`test_amount_is_immutable`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:259) | IM1–IM3 |
| One-shot guard | [`test_one_shot_prevents_second_payment`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:271) | BP2 |
| Project ▲ / funder ▼ | [`test_project_fund_increases_after_funding`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:286), [`test_funder_fund_decreases_after_funding`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:297) | SC6, SC7 |
| Closed period | [`test_operation_blocked_when_destination_in_closed_period`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:320), [`test_operation_blocked_when_source_in_closed_period`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_create.py:341) | VC10 |
| Reverse happy path | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:70), [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:76), [`test_reversal_is_reversal`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:83), [`test_reverse_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:89) | SR1–SR3 |
| Counter txs | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:96), [`test_reverse_counter_transactions_flip_funds`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:108), [`test_reverse_counter_transactions_preserve_type`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:118) | SR4–SR7 |
| Reverse constraints | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:129), [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:136) | VR1, VR2 |
| Balance restored | [`test_funder_fund_restored_after_reversal`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:155), [`test_project_fund_restored_after_reversal`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:146) | SR8 |
| Differential invariant | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/funding/test_project_funding_project_funding_reversal.py:168) | SR11, SR9 |

---

## 11. Tasks

- [x] Verify both `PROJECT_FUNDING_ISSUANCE` and `PROJECT_FUNDING_PAYMENT` are created on save
- [x] Verify transaction fund direction: `person.fund → project.fund` for both
- [x] Verify operation is fully settled immediately
- [x] Verify all validation branches VC1–VC16 (including balance check and shareholder check)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `create_payment_transaction()` is blocked after creation (one-shot)
- [x] Verify reversal creates counter-transactions: `project.fund → person.fund`
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify counter-transactions preserve transaction type
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [x] Verify funder balance affected correctly by create (▼ amount) and project (▲ amount)
- [x] Verify funder + project balances restored by reverse
- [x] UI: create form — source = person from URL, destination = project picker (shareholder-filtered)
- [x] UI: operation detail shows both transactions and reversal button
- [ ] Add a dedicated focused `test_reversal_clears_settlement_state` for Project Funding (SR9 currently pinned only by the differential invariant)
- [ ] Add a dedicated focused `test_reason_flows_to_reversal_description` for Project Funding (SR10 currently pinned only by the shared engine)
