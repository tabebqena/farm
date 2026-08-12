# Project Refund — Operation Contract

**Epic:** 9.2 — Project Capital Operations
**Type:** One-shot, auto-settled
**Actions:** `create`, `reverse`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Project Refund** operation.
> Every clause below is registered to its implementing code (model → mixin → transaction → view) and to its pinning test.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> Other operations follow the same structure — see [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md).

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.PROJECT_REFUND` (`"PROJECT_REFUND"`) | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:8) |
| Proxy class | `ProjectRefundOperation` | [`op_project_refund.py`](../../apps/app_operation/models/proxies/op_project_refund.py:8) |
| URL slug | `"project-refunding"` | [`op_project_refund.py`](../../apps/app_operation/models/proxies/op_project_refund.py:12) |
| Label | `"Project Refund"` | [`op_project_refund.py`](../../apps/app_operation/models/proxies/op_project_refund.py:13) |
| Theme | `success` / `bi-box-arrow-in-down` | [`op_project_refund.py`](../../apps/app_operation/models/proxies/op_project_refund.py:23) |
| Source role | `post` (must be a Project, picked from secondary field) | [`op_project_refund.py`](../../apps/app_operation/models/proxies/op_project_refund.py:14) |
| Destination role | `url` (must be a Person) | [`op_project_refund.py`](../../apps/app_operation/models/proxies/op_project_refund.py:15) |
| Registered in | `PROXY_MAP` | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:30) |
| Cross-op reference | row PR | [`operations-comparison.md`](operations-comparison.md) |

**Configuration flags** (all on [`op_project_refund.py`](../../apps/app_operation/models/proxies/op_project_refund.py:8)):

| Flag | Value | Meaning |
|------|-------|---------|
| `_issuance_transaction_type` | `PROJECT_REFUND_ISSUANCE` | issuance tx created on save |
| `_payment_transaction_type` | `PROJECT_REFUND_PAYMENT` | payment tx created on save (one-shot) |
| `_is_one_shot_operation` | `True` | payment fires at create; no standalone pay action |
| `can_pay` | `False` | `process_payment()` is a no-op |
| `is_partially_payable` | `False` | payment must equal amount (one-shot) |
| `max_payment_transaction_count` | `1` | exactly one payment tx ever |
| `check_balance_on_payment` | `False` (inherited default) | balance + investment-cap enforced by `clean()` at create, not per-payment |
| `has_category` / `category_required` | `False` | no financial category |
| `has_repayment` | `False` | no repayment action |
| `has_invoice` | `False` | no invoice items / no inventory movements |

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row links the clause to the code that must honor it.

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_source`/`clean_destination` + `clean()` (shareholder, balance, net-funded cap) | [`op_project_refund.py`](../../apps/app_operation/models/proxies/op_project_refund.py:8) |
| Project picker (`get_related_entities` — projects the URL person is a shareholder of) | [`op_project_refund.py`](../../apps/app_operation/models/proxies/op_project_refund.py:46) |
| Proxy registry / URL→class resolution | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:30) |
| Shared `Operation` engine (`clean`, `save`, `reverse`, `create`, `resolve_request`, period assignment, reversable tx types) | [`operation.py`](../../apps/app_operation/models/operation.py:34) |
| Operation type enum | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:8) |

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
| Payer balance check + net-funded cap at create | [`op_project_refund.py:clean()`](../../apps/app_operation/models/proxies/op_project_refund.py:88) |
| One-shot guard (single payment, amount == op.amount) | [`LinkedPaymentTransactionMixin.create_payment_transaction()`](../../apps/app_base/mixins.py:391) |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | [`ReversableModel`](../../apps/app_base/models.py:133) + [`Operation.reverse()`](../../apps/app_operation/models/operation.py:997) |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | [`models.py`](../../apps/app_transaction/models.py:33) |
| `PROJECT_REFUND_ISSUANCE` (project → shareholder) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:247), entity map [:535](../../apps/app_transaction/transaction_type.py:535), op map [:621](../../apps/app_transaction/transaction_type.py:621) |
| `PROJECT_REFUND_PAYMENT` (project → shareholder, affects balance) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:254), entity map [:536](../../apps/app_transaction/transaction_type.py:536), op map [:622](../../apps/app_transaction/transaction_type.py:622), payment set [:434](../../apps/app_transaction/transaction_type.py:434) |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Person balance = incoming payment txs − outgoing payment txs | [`Entity.balance`](../../apps/app_entity/models/__init__.py:668) → [`balance_at`](../../apps/app_entity/models/__init__.py:414) |
| Payables / receivables (one-shot nets to zero — SE4) | [`Entity.payables`](../../apps/app_entity/models/__init__.py:675), [`Entity.receivables`](../../apps/app_entity/models/__init__.py:681) |
| Balance enforcement: `can_pay` only balance-checks real (non-virtual) internal funds | [`Entity.can_pay`](../../apps/app_entity/models/__init__.py:704) |
| Role flags `is_person` / `is_project` | [`is_person`](../../apps/app_entity/models/__init__.py:273), [`is_project`](../../apps/app_entity/models/__init__.py:269) |
| Active-shareholder relationship (used by `clean()` + picker) | `Stakeholder` + `StakeholderRole.SHAREHOLDER` (see [`op_project_refund.py`](../../apps/app_operation/models/proxies/op_project_refund.py:76)) |
| Open financial period auto-created on entity creation | [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (generic, resolves `post` project source + URL person destination) | [`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:75) |
| POST parsing/validation | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) |
| Reverse view (reason required) | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) |
| Detail view (transactions + reversal button) | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) |
| URL: `/<pk>/<op_type>/create` | [`urls.py`](../../apps/app_operation/urls.py:142) |
| URL: `/<pk>/reverse/` | [`urls.py`](../../apps/app_operation/urls.py:192) |
| URL: `/<pk>/detail/` | [`urls.py`](../../apps/app_operation/urls.py:182) |
| Templates | [`generic_form.html`](../../apps/app_operation/templates/app_operation/generic_form.html), [`reverse_form.html`](../../apps/app_operation/templates/app_operation/reverse_form.html), [`operation_detail.html`](../../apps/app_operation/templates/app_operation/operation_detail.html), entry link in [`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html:36) |

### 2.6 Tests

| Concern | Test file |
|---------|-----------|
| Create branches | [`test_project_refund_project_refund_create.py`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py) |
| Reverse branches | [`test_project_refund_project_refund_reversal.py`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py) |
| Coverage manifest (executable branch registry) | [`tests/base.py`](../../apps/app_operation/tests/base.py:753) |

---

## 3. Money flow & entities

- **Source (payer):** the **Project** entity selected via the secondary field (`is_project=True`). Its fund is the source fund and is **balance-checked at create** (VC12).
- **Destination (receiver):** the **Person** (shareholder) entity in the URL (`is_person=True`). It must be a registered **active shareholder** of the source project (VC16), and the refund is capped by the shareholder's **net funded amount** into that project (VC17).
- **Transaction flow** (both on create, project → person):

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `PROJECT_REFUND_ISSUANCE` | `project.fund → person.fund` | none (issuance, not a payment type) |
| 2 | `PROJECT_REFUND_PAYMENT` | `project.fund → person.fund` | ▼ project by `amount`; ▲ shareholder by `amount` |

- **Payment source fund:** `self.source` (project) — [`op_project_refund.py`](../../apps/app_operation/models/proxies/op_project_refund.py:31)
- **Payment target fund:** `self.destination` (shareholder person) — [`op_project_refund.py`](../../apps/app_operation/models/proxies/op_project_refund.py:35)

---

## 4. Settlement model

Derived from [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:242) using payment-type transactions only:

| Property | After create | After reverse |
|----------|--------------|---------------|
| `amount_settled` | `== amount` | `0.00` |
| `total_settlable_amount` (`effective_amount`) | `== amount` (no adjustments) | unchanged |
| `amount_remaining_to_settle` | `0.00` | `== amount` |
| `is_fully_settled` | `True` | `False` |

Because the operation is one-shot and never adjustable, settlement is **immediate and terminal** — there is no standalone `pay` action. The immediate payment settles the issuance, so **payables/receivables net to zero** at all times (SE4/SR12).

---

## 5. Actions

### 5.1 `create`

Entry points: model `ProjectRefundOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx, then payment tx).

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source is Project | `source.is_project` | `ValidationError` | `"Project Refund source must be a Project entity."` | [`clean_source`](../../apps/app_operation/models/proxies/op_project_refund.py:61) | [`test_source_must_be_project_entity`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:160) |
| VC2 | Destination is Person | `destination.is_person` | `ValidationError` | `"Project Refund destination must be a Person entity."` | [`clean_destination`](../../apps/app_operation/models/proxies/op_project_refund.py:65) | [`test_destination_must_be_person_entity`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:166) |
| VC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | [`test_source_entity_must_be_active`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:194) |
| VC4 | Destination entity active | `destination.active` | `ValidationError` | same as VC3 | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | [`test_destination_entity_must_be_active`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:202) |
| VC5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | [`SourceFundMixin`](../../apps/app_base/mixins.py:132) | merged with VC3 ([`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:210)) |
| VC6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | [`TargetFundMixin`](../../apps/app_base/mixins.py:152) | merged with VC4 |
| VC7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | [`AmountCleanMixin`](../../apps/app_base/mixins.py:69) | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:222), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:227) |
| VC8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:81) | [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:263) |
| VC9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:84) | [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:271) |
| VC10 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:541) | covered by the shared period suite (see §10) |
| VC11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) | covered by the shared period suite (see §10) |
| VC12 | Balance checked at create (project pays) | `payment_source_fund.can_pay(amount)` | `ValidationError` | `"Insufficient project funds: balance is %(balance)s, cannot refund %(amount)s."` | [`op_project_refund.py:clean()`](../../apps/app_operation/models/proxies/op_project_refund.py:95) → [`Entity.can_pay`](../../apps/app_entity/models/__init__.py:704) | [`test_amount_exceeding_project_balance_raises_error`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:232), [`test_check_balance_on_payment_is_disabled`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:354) |
| VC13 | Tx entity-type contract | `source.is_project` and `target.is_person` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | [`Transaction.create()`](../../apps/app_transaction/models.py:144) + map [:535](../../apps/app_transaction/transaction_type.py:535) | implied by VC1/VC2 (model clean blocks first) |
| VC14 | Tx operation-type allowed | document is `PROJECT_REFUND` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | [`Transaction.create()`](../../apps/app_transaction/models.py:155) + map [:621](../../apps/app_transaction/transaction_type.py:621) | implied by VC1/VC2 |
| VC15 | Source ≠ target | project ≠ person | always true | `"Source and target funds must be different."` | [`Transaction.clean()`](../../apps/app_transaction/models.py:107) | structural (project ≠ person) |
| VC16 | Destination is active shareholder of source | an active `StakeholderRole.SHAREHOLDER` link exists from the source project to the destination | `ValidationError` | `"The refund destination must be a registered shareholder of the project."` | [`op_project_refund.py:clean()`](../../apps/app_operation/models/proxies/op_project_refund.py:76) | [`test_destination_must_be_shareholder_of_source_project`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:172) |
| VC17 | Refund ≤ net funded by shareholder | `amount <= total_funded − total_refunded` (unreversed `PROJECT_FUNDING` − unreversed `PROJECT_REFUND` for this project↔person pair) | `ValidationError` | `"Refund amount %(amount)s exceeds the net amount funded (%(net_refundable)s) by this shareholder."` | [`op_project_refund.py:clean()`](../../apps/app_operation/models/proxies/op_project_refund.py:100) | [`test_amount_exceeding_shareholder_funded_amount_raises_error`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:239), [`test_partial_refund_then_second_refund_exceeding_net_raises_error`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:245), [`test_amount_equal_to_funded_amount_succeeds`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:253) |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | 1 × `PROJECT_REFUND_ISSUANCE`, amount `== op.amount`, `project → person` | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:222) | [`test_creates_issuance_and_payment_transactions`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:99) |
| SC2 | Payment tx created | 1 × `PROJECT_REFUND_PAYMENT`, amount `== op.amount`, `project → person` | [`LinkedPaymentTransactionMixin.save()`](../../apps/app_base/mixins.py:424) | same as SC1 |
| SC3 | Tx amounts equal op amount | both txs `amount == op.amount` | transaction creation | [`test_transaction_amounts_match_operation`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:116) |
| SC4 | Tx fund direction | both txs `source=project`, `target=person` | [`op_project_refund.py`](../../apps/app_operation/models/proxies/op_project_refund.py:31) | [`test_transaction_funds_are_correct`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:123) |
| SC5 | Fully settled immediately | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:268) | [`test_is_fully_settled_after_creation`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:135) |
| SC6 | Project fund ▼ amount | `project.balance` decreases by `amount` | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) | [`test_project_fund_decreases_after_refund`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:328) |
| SC7 | Shareholder fund ▲ amount | `person.balance` increases by `amount` | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) | [`test_shareholder_fund_increases_after_refund`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:339) |
| SC8 | No invoice / no movements | `has_invoice=False`; no invoice items; no movement lines | `has_invoice=False` | config flag (`has_invoice=False`); no ledger/movement machinery in `post_save_tasks` |
| SC9 | Period auto-assigned | `period` = the shareholder's covering period (open period auto-created at entity creation) | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) + [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) | covered by shared period suite |
| SC10 | Payables/receivables net zero | immediate payment settles the issuance → `project.payables == 0`, `shareholder.receivables == 0` | one-shot auto-settlement | [`test_create_leaves_payables_receivables_zero`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:147) |

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:34) | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:147) |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:47) | [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:154) |
| VR3 | No explicit txs to reverse | all txs are implicit (one-shot issuance + payment) | `ValidationError` (would require manual reversal) | `"You can't reverse this object as it has non-reversed transactions…"` | [`ReversableModel._requires_transaction_reversal`](../../apps/app_base/models.py:203) + [`Operation._implicit_reversable_transaction_types`](../../apps/app_operation/models/operation.py:478) | implied by successful reverse ([`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:114)) |
| VR4 | No non-reversed adjustments | n/a — Project Refund is not adjustable | never fails | — | `is_adjustable=False` | n/a |
| VR5 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:82) | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:235) | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:88) |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:270) | [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:94) |
| SR3 | Reversal inherits identity | `amount`, `source`, `destination` copied | [`ReversableModel._get_reverse_kwargs`](../../apps/app_base/models.py:184) | [`test_reverse_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:107) |
| SR4 | Counter-tx for issuance | `person → project`, same amount, same type, `reversal_of=original` | [`Transaction.reverse()`](../../apps/app_transaction/models.py:206) | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:114) |
| SR5 | Counter-tx for payment | `person → project`, same amount, same type, `reversal_of=original` | same as SR4 | [`test_reverse_counter_transactions_flip_funds`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:126) |
| SR6 | Counter-txs preserve type + amount | `counter.type == original.type`, `counter.amount == original.amount` | same as SR4 | [`test_reverse_counter_transactions_preserve_type`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:136) |
| SR7 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:226) | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:120) |
| SR8 | Project + shareholder restored | `project.balance` and `person.balance` back to pre-create baseline | `balance_at` | [`test_project_fund_restored_after_reversal`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:164), [`test_shareholder_fund_restored_after_reversal`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:173) |
| SR9 | Settlement state cleared | `amount_settled == 0`, `is_fully_settled == False` | `amount_settled` | differential invariant ([`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:198)); no dedicated focused test yet (see §11) |
| SR10 | Reason flows to reversal | `reversal.description` contains the reason | [`ReversableModel.reverse()`](../../apps/app_base/models.py:262) | shared engine (see §11 — no dedicated focused test yet) |
| SR11 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger) | whole engine | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:198) |
| SR12 | Payables/receivables stay zero | reversal mirrors must not leak into the buckets → both remain `0.00` | one-shot auto-settlement | [`test_reverse_leaves_payables_receivables_zero`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:186) |

### 5.3 `pay` (one-shot guard)

There is **no standalone pay action** for Project Refund:

| Branch | Behavior | Enforced by | Pinned by test |
|--------|----------|-------------|----------------|
| `process_payment()` called | no-op (returns immediately — `can_pay=False`) | [`process_payment`](../../apps/app_operation/models/operation.py:686) | n/a (covered by `can_pay=False`) |
| `create_payment_transaction()` called after create | `ValidationError` — one-shot allows a single payment only, amount must equal `op.amount` (balance re-checked first, VC12) | [`create_payment_transaction`](../../apps/app_base/mixins.py:391) | [`test_one_shot_prevents_second_payment`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:313) |

### 5.4 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by [`ImmutableMixin`](../../apps/app_base/mixins.py:30) via `_immutable_fields` ([`operation.py`](../../apps/app_operation/models/operation.py:51)).

| Branch | Enforced by | Pinned by test |
|--------|-------------|----------------|
| `source` changed after save | `ImmutableMixin.save()` | [`test_source_is_immutable`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:283) |
| `destination` changed after save | `ImmutableMixin.save()` | [`test_destination_is_immutable`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:292) |
| `amount` changed after save | `ImmutableMixin.save()` | [`test_amount_is_immutable`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:301) |

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — [`Entity.save()`](../../apps/app_entity/models/__init__.py:714).
- The operation's governing entity (`period_entity`) is the **destination shareholder person** (`_dest_role = "url"`) — [`Operation.period_entity`](../../apps/app_operation/models/operation.py:500).
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC11).
- New operations dated inside a **closed** period are rejected (VC10) — [`is_date_in_closed_period`](../../apps/app_operation/models/period.py:14).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period ([`_reverse_period`](../../apps/app_operation/models/operation.py:455)).

---

## 7. Entity roles & balance contract

- Project is the only allowed source; person (shareholder) the only allowed destination — enforced at model (VC1/VC2/VC16) and transaction (VC13) layers.
- The destination must be a registered **active shareholder** of the source project (VC16) — enforced in `clean()` via the project's `stakeholders` relation.
- Refunds are capped by the shareholder's **net funded amount** into the project (VC17) — computed in `clean()` as unreversed `PROJECT_FUNDING` minus unreversed `PROJECT_REFUND` for the project↔person pair.
- `project.balance` / `person.balance` are derived exclusively from **payment-type** transactions (`balance_at`); the issuance tx never moves a balance.
- The project fund is a **real internal fund** and is balance-checked at create (`clean()`, VC12). `check_balance_on_payment` stays `False` — the balance + cap are guaranteed once at creation, and the one-shot payment then matches it exactly.
- Project Refund is the mirror of Project Funding (PF): PF moves `person → project` (funder pays), PR moves `project → person` (project pays, capped by net funded).

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Create route | `POST/GET /<person_pk>/project-refunding/create` → [`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:75) |
| Source selection | a **Project** picked from the secondary field (`_source_role="post"`); [`get_related_entities`](../../apps/app_operation/models/proxies/op_project_refund.py:46) returns the projects for which the URL person is an active shareholder |
| Destination selection | the **Person (shareholder)** from the URL (`_dest_role="url"`, resolved by [`resolve_request`](../../apps/app_operation/models/operation.py:202)); no picker |
| Category | hidden (no category) |
| Amount | raw `amount` POST field ([`_compute_amount`](../../apps/app_operation/views/create_operation/base.py:52)); validated > 0 at model; balance- and cap-checked at create (VC12/VC17) |
| POST parsing | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) — date format, description, category (n/a), `amount_paid` (n/a, forced 0) |
| List entry | "Project ReFunding" link in [`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html:36) (template label text) |
| Detail | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) — shows both transactions + settlement + reversal button |
| Reverse | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source=project · VC2 dest=person · VC3 source active · VC4 dest active · VC5 source fund active · VC6 target fund active · VC7 amount>0 · VC8 officer staff · VC9 officer active · VC10 not closed-period · VC11 covering period exists · VC12 balance checked (clean) · VC13 tx entity-type · VC14 tx op-type · VC15 source≠target · VC16 dest is active shareholder of source · VC17 refund ≤ net funded

**create — effects:** SC1 issuance tx · SC2 payment tx · SC3 amounts equal · SC4 direction project→person · SC5 settled immediately · SC6 project ▼ · SC7 shareholder ▲ · SC8 no invoice/movements · SC9 period assigned · SC10 payables/receivables net zero

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no explicit txs · VR4 no adjustments (n/a) · VR5 reason required (view)

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 identity copied · SR4 issuance counter-tx · SR5 payment counter-tx · SR6 type/amount preserved · SR7 reversal owns no txs · SR8 project+shareholder restored · SR9 settlement cleared · SR10 reason in description · SR11 differential invariant · SR12 payables/receivables stay zero

**pay / immutability:** BP1 `process_payment` no-op · BP2 `create_payment_transaction` blocked after create · IM1/IM2/IM3 source/destination/amount immutable

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| Tx creation + counts | [`test_creates_issuance_and_payment_transactions`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:99) | SC1, SC2 |
| Tx amounts | [`test_transaction_amounts_match_operation`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:116) | SC3 |
| Tx direction | [`test_transaction_funds_are_correct`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:123) | SC4 |
| Settlement | [`test_is_fully_settled_after_creation`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:135) | SC5 |
| Payables/receivables | [`test_create_leaves_payables_receivables_zero`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:147) | SC10 |
| Source/dest validation | [`test_source_must_be_project_entity`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:160), [`test_destination_must_be_person_entity`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:166) | VC1, VC2 |
| Shareholder check | [`test_destination_must_be_shareholder_of_source_project`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:172) | VC16 |
| Active entities | [`test_source_entity_must_be_active`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:194), [`test_destination_entity_must_be_active`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:202), [`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:210) | VC3–VC6 |
| Amount | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:222), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:227) | VC7 |
| Balance check | [`test_amount_exceeding_project_balance_raises_error`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:232), [`test_check_balance_on_payment_is_disabled`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:354) | VC12 |
| Net-funded cap | [`test_amount_exceeding_shareholder_funded_amount_raises_error`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:239), [`test_partial_refund_then_second_refund_exceeding_net_raises_error`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:245), [`test_amount_equal_to_funded_amount_succeeds`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:253) | VC17 |
| Officer | [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:263), [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:271) | VC8, VC9 |
| Immutability | [`test_source_is_immutable`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:283), [`test_destination_is_immutable`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:292), [`test_amount_is_immutable`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:301) | IM1–IM3 |
| One-shot guard | [`test_one_shot_prevents_second_payment`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:313) | BP2 |
| Project ▼ / shareholder ▲ | [`test_project_fund_decreases_after_refund`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:328), [`test_shareholder_fund_increases_after_refund`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_create.py:339) | SC6, SC7 |
| Reverse happy path | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:88), [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:94), [`test_reversal_is_reversal`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:101), [`test_reverse_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:107) | SR1–SR3 |
| Counter txs | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:114), [`test_reverse_counter_transactions_flip_funds`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:126), [`test_reverse_counter_transactions_preserve_type`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:136) | SR4–SR7 |
| Reverse constraints | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:147), [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:154) | VR1, VR2 |
| Balance restored | [`test_project_fund_restored_after_reversal`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:164), [`test_shareholder_fund_restored_after_reversal`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:173) | SR8 |
| Payables/receivables through reversal | [`test_reverse_leaves_payables_receivables_zero`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:186) | SR12 |
| Differential invariant | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/funding/test_project_refund_project_refund_reversal.py:198) | SR11, SR9 |

---

## 11. Tasks

- [x] Verify both `PROJECT_REFUND_ISSUANCE` and `PROJECT_REFUND_PAYMENT` are created on save
- [x] Verify transaction fund direction: `project.fund → person.fund` for both
- [x] Verify operation is fully settled immediately
- [x] Verify all validation branches VC1–VC17 (including balance check, shareholder check, and net-funded cap)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `create_payment_transaction()` is blocked after creation (one-shot)
- [x] Verify reversal creates counter-transactions: `person.fund → project.fund`
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify counter-transactions preserve transaction type
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [x] Verify project balance affected correctly by create (▼ amount) and shareholder (▲ amount)
- [x] Verify project + shareholder balances restored by reverse
- [x] Verify payables/receivables net to zero at create and stay zero through reversal (SE4/SR12)
- [x] UI: create form — source = project picker (shareholder-filtered), destination = person from URL
- [x] UI: operation detail shows both transactions and reversal button
- [ ] Add a dedicated focused `test_reversal_clears_settlement_state` for Project Refund (SR9 currently pinned only by the differential invariant)
- [ ] Add a dedicated focused `test_reason_flows_to_reversal_description` for Project Refund (SR10 currently pinned only by the shared engine)
