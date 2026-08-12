# Correction (Credit & Debit) — Operation Contract

**Epic:** 10.x — Miscellaneous One-Shot Operations
**Type:** One-shot, auto-settled
**Actions:** `create`, `reverse`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Correction** operations — **Correction Credit** (CC) and **Correction Debit** (CD).
> Every clause below is registered to its implementing code (model → mixin → transaction → view) and to its pinning test.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> Both variants are **admin-only tools** for fixing wrong calculations: neither has a category, neither is balance-gated, and both settle immediately on save.
> Other operations follow the same structure — see [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md).

---

## 1. Identity

| Field | Correction Credit | Correction Debit | Defined in |
|-------|-------------------|------------------|-----------|
| Operation type | `OperationType.CORRECTION_CREDIT` | `OperationType.CORRECTION_DEBIT` | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:19) / [:20](../../apps/app_operation/models/operation_type.py:20) |
| Proxy class | `CorrectionCreditOperation` | `CorrectionDebitOperation` | [`op_correction_credit.py`](../../apps/app_operation/models/proxies/op_correction_credit.py:7) / [`op_correction_debit.py`](../../apps/app_operation/models/proxies/op_correction_debit.py:7) |
| URL slug | `"correction-credit"` | `"correction-debit"` | [`op_correction_credit.py:11`](../../apps/app_operation/models/proxies/op_correction_credit.py:11) / [`op_correction_debit.py:11`](../../apps/app_operation/models/proxies/op_correction_debit.py:11) |
| Label | `"Correction Credit"` | `"Correction Debit"` | [`op_correction_credit.py:12`](../../apps/app_operation/models/proxies/op_correction_credit.py:12) / [`op_correction_debit.py:12`](../../apps/app_operation/models/proxies/op_correction_debit.py:12) |
| Theme | `success` / `bi-patch-plus` | `danger` / `bi-patch-minus` | [`op_correction_credit.py:26`](../../apps/app_operation/models/proxies/op_correction_credit.py:26) / [`op_correction_debit.py:26`](../../apps/app_operation/models/proxies/op_correction_debit.py:26) |
| Source role | `system` | `url` (must be a Project) | [`op_correction_credit.py:13`](../../apps/app_operation/models/proxies/op_correction_credit.py:13) / [`op_correction_debit.py:13`](../../apps/app_operation/models/proxies/op_correction_debit.py:13) |
| Destination role | `url` (must be a Project) | `system` | [`op_correction_credit.py:14`](../../apps/app_operation/models/proxies/op_correction_credit.py:14) / [`op_correction_debit.py:14`](../../apps/app_operation/models/proxies/op_correction_debit.py:14) |
| Registered in | `PROXY_MAP` | `PROXY_MAP` | [`proxies/__init__.py:42`](../../apps/app_operation/models/proxies/__init__.py:42) / [:43](../../apps/app_operation/models/proxies/__init__.py:43) |
| Cross-op reference | row CC | row CD | [`operations-comparison.md`](operations-comparison.md) |

**Configuration flags:**

| Flag | Correction Credit | Correction Debit | Meaning |
|------|-------------------|------------------|---------|
| `_issuance_transaction_type` | `CORRECTION_CREDIT_ISSUANCE` | `CORRECTION_DEBIT_ISSUANCE` | issuance tx created on save |
| `_payment_transaction_type` | `CORRECTION_CREDIT_PAYMENT` | `CORRECTION_DEBIT_PAYMENT` | payment tx created on save (one-shot) |
| `_is_one_shot_operation` | `True` | `True` | payment fires at create; no standalone pay action |
| `can_pay` | `False` | `False` | `process_payment()` is a no-op |
| `is_partially_payable` | `False` | `False` | payment must equal amount (one-shot) |
| `max_payment_transaction_count` | `1` | `1` | exactly one payment tx ever |
| `check_balance_on_payment` | `False` (explicit) | `False` (explicit) | no balance gate — admin tool, may go into deficit |
| `has_category` / `category_required` | `False` | `False` | no financial category |
| `has_repayment` | `False` | `False` | no repayment action |
| `has_invoice` | `False` | `False` | no invoice items / no inventory movements |

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row links the clause to the code that must honor it.

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Credit proxy + config + `clean_source`/`clean_destination` | [`op_correction_credit.py`](../../apps/app_operation/models/proxies/op_correction_credit.py:7) |
| Debit proxy + config + `clean_source`/`clean_destination` | [`op_correction_debit.py`](../../apps/app_operation/models/proxies/op_correction_debit.py:7) |
| Proxy registry / URL→class resolution | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:42) |
| Shared `Operation` engine (`clean`, `save`, `reverse`, `create`, `resolve_request`, period assignment, reversable tx types) | [`operation.py`](../../apps/app_operation/models/operation.py:34) |
| Operation type enum | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:19) |

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
| Balance exemption (no per-payment gate — `check_balance_on_payment=False`) | [`LinkedPaymentTransactionMixin.create_payment_transaction()`](../../apps/app_base/mixins.py:377) skips the gate |
| One-shot guard (single payment, amount == op.amount) | [`LinkedPaymentTransactionMixin.create_payment_transaction()`](../../apps/app_base/mixins.py:391) |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | [`ReversableModel`](../../apps/app_base/models.py:133) + [`Operation.reverse()`](../../apps/app_operation/models/operation.py:997) |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | [`models.py`](../../apps/app_transaction/models.py:33) |
| `CORRECTION_CREDIT_ISSUANCE` / `_PAYMENT` (system → project) | [`transaction_type.py:328`](../../apps/app_transaction/transaction_type.py:328) / [:338](../../apps/app_transaction/transaction_type.py:338), entity map [:550](../../apps/app_transaction/transaction_type.py:550)/[:551](../../apps/app_transaction/transaction_type.py:551), op map [:632](../../apps/app_transaction/transaction_type.py:632)/[:633](../../apps/app_transaction/transaction_type.py:633), payment set [:438](../../apps/app_transaction/transaction_type.py:438) |
| `CORRECTION_DEBIT_ISSUANCE` / `_PAYMENT` (project → system) | [`transaction_type.py:348`](../../apps/app_transaction/transaction_type.py:348) / [:358](../../apps/app_transaction/transaction_type.py:358), entity map [:552](../../apps/app_transaction/transaction_type.py:552)/[:553](../../apps/app_transaction/transaction_type.py:553), op map [:634](../../apps/app_transaction/transaction_type.py:634)/[:635](../../apps/app_transaction/transaction_type.py:635), payment set [:439](../../apps/app_transaction/transaction_type.py:439) |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Project balance = incoming payment txs − outgoing payment txs | [`Entity.balance`](../../apps/app_entity/models/__init__.py:668) → [`balance_at`](../../apps/app_entity/models/__init__.py:414) |
| `is_system` / `is_project` role flags (used by `clean_source`/`clean_destination`) | [`is_system`](../../apps/app_entity/models/__init__.py:257), [`is_project`](../../apps/app_entity/models/__init__.py:269) |
| Virtual-entity payment exemption (system never balance-checked) | [`Entity.can_pay`](../../apps/app_entity/models/__init__.py:704) |
| Open financial period auto-created on entity creation | [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (generic, resolves system/url roles) | [`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:75) |
| POST parsing/validation | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) |
| Reverse view (reason required) | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) |
| Detail view (transactions + reversal button) | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) |
| URL: `/<pk>/<op_type>/create` | [`urls.py`](../../apps/app_operation/urls.py:142) |
| URL: `/<pk>/reverse/` | [`urls.py`](../../apps/app_operation/urls.py:192) |
| URL: `/<pk>/detail/` | [`urls.py`](../../apps/app_operation/urls.py:182) |
| Templates | [`generic_form.html`](../../apps/app_operation/templates/app_operation/generic_form.html), [`reverse_form.html`](../../apps/app_operation/templates/app_operation/reverse_form.html), [`operation_detail.html`](../../apps/app_operation/templates/app_operation/operation_detail.html). No standard dropdown entry in [`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html) — admin-only routes |

### 2.6 Tests

| Concern | Test file |
|---------|-----------|
| Credit create branches | [`test_correction_correction_credit_create.py`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py) |
| Credit reverse branches | [`test_correction_correction_credit_reversal.py`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py) |
| Debit create branches | [`test_correction_correction_debit_create.py`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py) |
| Debit reverse branches | [`test_correction_correction_debit_reversal.py`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py) |
| Coverage manifest (executable branch registry) | [`tests/base.py`](../../apps/app_operation/tests/base.py:851) (CC) / [:871](../../apps/app_operation/tests/base.py:871) (CD) |

---

## 3. Money flow & entities

### Correction Credit (CC)

- **Source (payer):** the **System** entity (`is_system=True`). Virtual — never balance-checked, exempt from period checks (system has no periods).
- **Destination (receiver):** the **Project** entity in the URL (`is_project=True`). Its fund is the target fund.
- **Transaction flow** (both on create, system → project):

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `CORRECTION_CREDIT_ISSUANCE` | `system.fund → project.fund` | none (issuance, not a payment type) |
| 2 | `CORRECTION_CREDIT_PAYMENT` | `system.fund → project.fund` | ▲ project by `amount` |

- **Payment source fund:** `self.source` (system) — [`op_correction_credit.py`](../../apps/app_operation/models/proxies/op_correction_credit.py:34)
- **Payment target fund:** `self.destination` (project) — [`op_correction_credit.py`](../../apps/app_operation/models/proxies/op_correction_credit.py:38)

### Correction Debit (CD)

- **Source (payer):** the **Project** entity in the URL (`is_project=True`). Its fund is the source fund.
- **Destination (receiver):** the **System** entity (`is_system=True`). Virtual — never balance-checked.
- **Transaction flow** (both on create, project → system):

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `CORRECTION_DEBIT_ISSUANCE` | `project.fund → system.fund` | none (issuance, not a payment type) |
| 2 | `CORRECTION_DEBIT_PAYMENT` | `project.fund → system.fund` | ▼ project by `amount` |

- **Payment source fund:** `self.source` (project) — [`op_correction_debit.py`](../../apps/app_operation/models/proxies/op_correction_debit.py:34)
- **Payment target fund:** `self.destination` (system) — [`op_correction_debit.py`](../../apps/app_operation/models/proxies/op_correction_debit.py:38)

---

## 4. Settlement model

Derived from [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:242) using payment-type transactions only:

| Property | After create | After reverse |
|----------|--------------|---------------|
| `amount_settled` | `== amount` | `0.00` |
| `total_settlable_amount` (`effective_amount`) | `== amount` (no adjustments) | unchanged |
| `amount_remaining_to_settle` | `0.00` | `== amount` |
| `is_fully_settled` | `True` | `False` |

Because both operations are one-shot and never adjustable, settlement is **immediate and terminal** — there is no standalone `pay` action.

---

## 5. Actions

### 5.1 `create` — Correction Credit

Entry points: model `CorrectionCreditOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx, then payment tx).

#### 5.1.1 Validation branches (CC)

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| CC1 | Source is System | `source.is_system` | `ValidationError` | `"Correction Credit source must be the System entity."` | [`clean_source`](../../apps/app_operation/models/proxies/op_correction_credit.py:41) | [`test_source_must_be_system_entity`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:127), [`test_source_world_entity_raises_validation_error`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:133) |
| CC2 | Destination is Project | `destination.is_project` | `ValidationError` | `"Correction Credit destination must be a Project entity."` | [`clean_destination`](../../apps/app_operation/models/proxies/op_correction_credit.py:45) | [`test_destination_must_be_project_entity`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:159) |
| CC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | [`test_source_must_be_active`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:139) |
| CC4 | Destination entity active | `destination.active` | `ValidationError` | same as CC3 | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | [`test_destination_must_be_active`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:165) |
| CC5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | [`SourceFundMixin`](../../apps/app_base/mixins.py:132) | merged with CC3 ([`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:147)) |
| CC6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | [`TargetFundMixin`](../../apps/app_base/mixins.py:152) | merged with CC4 |
| CC7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | [`AmountCleanMixin`](../../apps/app_base/mixins.py:69) | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:177), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:182) |
| CC8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:81) | [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:190) |
| CC9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:84) | [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:198) |
| CC10 | Date not in a closed period (destination) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:541) | covered by the shared period suite (see §10) |
| CC11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) | covered by the shared period suite (see §10) |
| CC12 | Balance exempt (system payer) | no balance check | never fails | — | `check_balance_on_payment=False` (explicit) + system is virtual | [`test_check_balance_on_payment_is_disabled`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:258) |
| CC13 | Tx entity-type contract | `source.is_system` and `target.is_project` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | [`Transaction.create()`](../../apps/app_transaction/models.py:144) + map [:550](../../apps/app_transaction/transaction_type.py:550) | implied by CC1/CC2 (model clean blocks first) |
| CC14 | Tx operation-type allowed | document is `CORRECTION_CREDIT` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | [`Transaction.create()`](../../apps/app_transaction/models.py:155) + map [:632](../../apps/app_transaction/transaction_type.py:632) | implied by CC1/CC2 |
| CC15 | No category required | `category_required=False` | never fails | — | `has_category=False` | [`test_no_category_config`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:119) |

#### 5.1.2 Success effects (CC)

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| CC16 | Issuance tx created | 1 × `CORRECTION_CREDIT_ISSUANCE`, amount `== op.amount`, `system → project` | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:222) | [`test_creates_issuance_and_payment_transactions`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:78) |
| CC17 | Payment tx created | 1 × `CORRECTION_CREDIT_PAYMENT`, amount `== op.amount`, `system → project` | [`LinkedPaymentTransactionMixin.save()`](../../apps/app_base/mixins.py:424) | same as CC16 |
| CC18 | Tx fund direction | both txs `source=system`, `target=project` | [`op_correction_credit.py`](../../apps/app_operation/models/proxies/op_correction_credit.py:34) | [`test_transaction_funds_are_correct`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:91) |
| CC19 | Fully settled immediately | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:268) | [`test_is_fully_settled_after_creation`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:99) |
| CC20 | Project fund ▲ amount | `project.balance` increases by `amount` | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) | [`test_project_fund_increases_by_correction_amount`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:107) |
| CC21 | System (virtual) ▼ | system balance moves but is never enforced / never read for checks | `can_pay` virtual exemption | differential invariant ([`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:141)) |
| CC22 | No invoice / no movements | `has_invoice=False`; no invoice items; no movement lines | `has_invoice=False` | config flag |
| CC23 | Period auto-assigned | `period` = the project's covering period (open period auto-created at entity creation) | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) + [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) | covered by shared period suite |

### 5.2 `reverse` — Correction Credit

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches (CC)

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| CC24 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:34) | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:162) |
| CC25 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:47) | [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:169) |
| CC26 | No explicit txs to reverse | all txs are implicit (one-shot issuance + payment) | `ValidationError` (would require manual reversal) | `"You can't reverse this object as it has non-reversed transactions…"` | [`ReversableModel._requires_transaction_reversal`](../../apps/app_base/models.py:203) + [`Operation._implicit_reversable_transaction_types`](../../apps/app_operation/models/operation.py:478) | implied by successful reverse ([`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:101)) |
| CC27 | No non-reversed adjustments | n/a — not adjustable | never fails | — | `is_adjustable=False` | n/a |
| CC28 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:82) | view contract (see §8) |

#### 5.2.2 Success effects (CC)

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| CC29 | Reversal record created | cloned op, `reversal_of = original` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:235) | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:75) |
| CC30 | Original marked reversed | `original.reversed_by = reversal` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:270) | [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:81) |
| CC31 | Reversal inherits identity | `amount`, `source`, `destination` copied | [`ReversableModel._get_reverse_kwargs`](../../apps/app_base/models.py:184) | [`test_reversal_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:94) |
| CC32 | Counter-tx for issuance | `project → system`, same amount, same type, `reversal_of=original` | [`Transaction.reverse()`](../../apps/app_transaction/models.py:206) | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:101) |
| CC33 | Counter-tx for payment | `project → system`, same amount, same type, `reversal_of=original` | same as CC32 | [`test_reverse_counter_transactions_flip_funds`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:110) |
| CC34 | Counter-txs preserve type | `counter.type == original.type` | same as CC32 | [`test_reverse_counter_transactions_preserve_type`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:120) |
| CC35 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:226) | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:105) |
| CC36 | Project fund restored | `project.balance` back to pre-create baseline | `balance_at` | [`test_project_fund_restored_after_reversal`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:127) |
| CC37 | Settlement state cleared | `amount_settled == 0`, `is_fully_settled == False` | `amount_settled` | differential invariant ([`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:141)); no dedicated focused test yet (see §11) |
| CC38 | Reason flows to reversal | `reversal.description` contains the reason | [`ReversableModel.reverse()`](../../apps/app_base/models.py:262) | shared engine (see §11 — no dedicated focused test yet) |
| CC39 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger) | whole engine | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:141) |

### 5.3 `create` — Correction Debit

Entry points: model `CorrectionDebitOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx, then payment tx).

#### 5.3.1 Validation branches (CD)

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| CD1 | Source is Project | `source.is_project` | `ValidationError` | `"Correction Debit source must be a Project entity."` | [`clean_source`](../../apps/app_operation/models/proxies/op_correction_debit.py:41) | [`test_source_must_be_project_entity`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:136), [`test_source_system_entity_raises_validation_error`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:142) |
| CD2 | Destination is System | `destination.is_system` | `ValidationError` | `"Correction Debit destination must be the System entity."` | [`clean_destination`](../../apps/app_operation/models/proxies/op_correction_debit.py:45) | [`test_destination_must_be_system_entity`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:167), [`test_destination_world_entity_raises_validation_error`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:173) |
| CD3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | [`test_source_must_be_active`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:147) |
| CD4 | Destination entity active | `destination.active` | `ValidationError` | same as CD3 | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | [`test_destination_must_be_active`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:179) |
| CD5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | [`SourceFundMixin`](../../apps/app_base/mixins.py:132) | merged with CD3 ([`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:155)) |
| CD6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | [`TargetFundMixin`](../../apps/app_base/mixins.py:152) | merged with CD4 (system always active) |
| CD7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | [`AmountCleanMixin`](../../apps/app_base/mixins.py:69) | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:191), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:196) |
| CD8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:81) | [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:205) |
| CD9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:84) | [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:213) |
| CD10 | Date not in a closed period (source) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:541) | covered by the shared period suite (see §10) |
| CD11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) | covered by the shared period suite (see §10) |
| CD12 | Balance exempt (admin tool) | no balance check — debit may drive the fund into deficit | never fails | — | `check_balance_on_payment=False` (explicit) | [`test_check_balance_on_payment_is_disabled`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:258), [`test_debit_succeeds_even_with_insufficient_balance`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:262) |
| CD13 | Tx entity-type contract | `source.is_project` and `target.is_system` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | [`Transaction.create()`](../../apps/app_transaction/models.py:144) + map [:552](../../apps/app_transaction/transaction_type.py:552) | implied by CD1/CD2 (model clean blocks first) |
| CD14 | Tx operation-type allowed | document is `CORRECTION_DEBIT` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | [`Transaction.create()`](../../apps/app_transaction/models.py:155) + map [:634](../../apps/app_transaction/transaction_type.py:634) | implied by CD1/CD2 |
| CD15 | No category required | `category_required=False` | never fails | — | `has_category=False` | [`test_no_category_config`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:128) |

#### 5.3.2 Success effects (CD)

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| CD16 | Issuance tx created | 1 × `CORRECTION_DEBIT_ISSUANCE`, amount `== op.amount`, `project → system` | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:222) | [`test_creates_issuance_and_payment_transactions`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:86) |
| CD17 | Payment tx created | 1 × `CORRECTION_DEBIT_PAYMENT`, amount `== op.amount`, `project → system` | [`LinkedPaymentTransactionMixin.save()`](../../apps/app_base/mixins.py:424) | same as CD16 |
| CD18 | Tx fund direction | both txs `source=project`, `target=system` | [`op_correction_debit.py`](../../apps/app_operation/models/proxies/op_correction_debit.py:34) | [`test_transaction_funds_are_correct`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:99) |
| CD19 | Fully settled immediately | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:268) | [`test_is_fully_settled_after_creation`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:107) |
| CD20 | Project fund ▼ amount | `project.balance` decreases by `amount` | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) | [`test_project_fund_decreases_by_correction_amount`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:115) |
| CD21 | System (virtual) ▲ | system balance moves but is never enforced / never read for checks | `can_pay` virtual exemption | differential invariant ([`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:148)) |
| CD22 | No invoice / no movements | `has_invoice=False`; no invoice items; no movement lines | `has_invoice=False` | config flag |
| CD23 | Period auto-assigned | `period` = the project's covering period (open period auto-created at entity creation) | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) + [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) | covered by shared period suite |

### 5.4 `reverse` — Correction Debit

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.4.1 Validation branches (CD)

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| CD24 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:34) | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:169) |
| CD25 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:47) | [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:176) |
| CD26 | No explicit txs to reverse | all txs are implicit (one-shot issuance + payment) | `ValidationError` (would require manual reversal) | `"You can't reverse this object as it has non-reversed transactions…"` | [`ReversableModel._requires_transaction_reversal`](../../apps/app_base/models.py:203) + [`Operation._implicit_reversable_transaction_types`](../../apps/app_operation/models/operation.py:478) | implied by successful reverse ([`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:108)) |
| CD27 | No non-reversed adjustments | n/a — not adjustable | never fails | — | `is_adjustable=False` | n/a |
| CD28 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:82) | view contract (see §8) |

#### 5.4.2 Success effects (CD)

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| CD29 | Reversal record created | cloned op, `reversal_of = original` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:235) | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:82) |
| CD30 | Original marked reversed | `original.reversed_by = reversal` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:270) | [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:88) |
| CD31 | Reversal inherits identity | `amount`, `source`, `destination` copied | [`ReversableModel._get_reverse_kwargs`](../../apps/app_base/models.py:184) | [`test_reversal_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:101) |
| CD32 | Counter-tx for issuance | `system → project`, same amount, same type, `reversal_of=original` | [`Transaction.reverse()`](../../apps/app_transaction/models.py:206) | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:108) |
| CD33 | Counter-tx for payment | `system → project`, same amount, same type, `reversal_of=original` | same as CD32 | [`test_reverse_counter_transactions_flip_funds`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:117) |
| CD34 | Counter-txs preserve type | `counter.type == original.type` | same as CD32 | [`test_reverse_counter_transactions_preserve_type`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:127) |
| CD35 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:226) | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:112) |
| CD36 | Project fund restored | `project.balance` back to pre-create baseline | `balance_at` | [`test_project_fund_restored_after_reversal`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:134) |
| CD37 | Settlement state cleared | `amount_settled == 0`, `is_fully_settled == False` | `amount_settled` | differential invariant ([`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:148)); no dedicated focused test yet (see §11) |
| CD38 | Reason flows to reversal | `reversal.description` contains the reason | [`ReversableModel.reverse()`](../../apps/app_base/models.py:262) | shared engine (see §11 — no dedicated focused test yet) |
| CD39 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger) | whole engine | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:148) |

### 5.5 `pay` (one-shot guard) — both

There is **no standalone pay action** for either Correction variant:

| Branch | Behavior | Enforced by | Pinned by test |
|--------|----------|-------------|----------------|
| `process_payment()` called | no-op (returns immediately — `can_pay=False`) | [`process_payment`](../../apps/app_operation/models/operation.py:686) | n/a (covered by `can_pay=False`) |
| `create_payment_transaction()` called after create | `ValidationError` — one-shot allows a single payment only, amount must equal `op.amount` | [`create_payment_transaction`](../../apps/app_base/mixins.py:391) | [`test_one_shot_prevents_second_payment`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:243), [`test_one_shot_prevents_second_payment`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:277) |
| `can_pay` flag | `False` on both proxies | class config | [`test_can_pay_is_false`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:240), [`test_can_pay_is_false`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:274) |

### 5.6 Immutability — both

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by [`ImmutableMixin`](../../apps/app_base/mixins.py:30) via `_immutable_fields` ([`operation.py`](../../apps/app_operation/models/operation.py:51)).

| Branch | Enforced by | Credit pinned by | Debit pinned by |
|--------|-------------|------------------|-----------------|
| `source` changed after save | `ImmutableMixin.save()` | [`test_source_is_immutable`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:210) | [`test_source_is_immutable`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:225) |
| `destination` changed after save | `ImmutableMixin.save()` | [`test_destination_is_immutable`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:219) | [`test_destination_is_immutable`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:237) |
| `amount` changed after save | `ImmutableMixin.save()` | [`test_amount_is_immutable`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:228) | [`test_amount_is_immutable`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:246) |

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — [`Entity.save()`](../../apps/app_entity/models/__init__.py:714).
- The operation's governing entity (`period_entity`) is the **project** (Credit: `_dest_role = "url"`; Debit: `_source_role = "url"`) — [`Operation.period_entity`](../../apps/app_operation/models/operation.py:498).
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (CC11/CD11).
- New operations dated inside a **closed** period are rejected (CC10/CD10) — [`is_date_in_closed_period`](../../apps/app_operation/models/period.py:14).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period ([`_reverse_period`](../../apps/app_operation/models/operation.py:455)).

---

## 7. Entity roles & balance contract

- **Credit:** system is the only allowed source; project the only allowed destination — enforced at model (CC1/CC2) and transaction (CC13) layers.
- **Debit:** project is the only allowed source; system the only allowed destination — enforced at model (CD1/CD2) and transaction (CD13) layers.
- `project.balance` is derived exclusively from **payment-type** transactions (`balance_at`); the issuance tx never moves a balance.
- System is **virtual**: `can_pay` always returns `True`, so neither variant is ever blocked by fund balance (CC12/CD12). In particular, a **Correction Debit may drive the project fund into deficit** — this is intentional (admin tool for fixing ledger errors) and pinned by `test_debit_succeeds_even_with_insufficient_balance`.
- Corrections carry **no category** and **no invoice/movements** — they touch only balances (CC15/CD15).

---

## 8. View / UI contract

| Concern | Correction Credit | Correction Debit |
|---------|-------------------|------------------|
| Create route | `POST/GET /<project_pk>/correction-credit/create` → [`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:75) | `POST/GET /<project_pk>/correction-debit/create` → [`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:75) |
| Source selection | locked to the **System** entity (`_source_role="system"`, resolved by [`resolve_request`](../../apps/app_operation/models/operation.py:202)); no picker | the **Project** from the URL (`_source_role="url"`); no picker |
| Destination selection | the **Project** from the URL (`_dest_role="url"`); no secondary-entity field | locked to the **System** entity (`_dest_role="system"`); no picker |
| Category | hidden (no category) | hidden (no category) |
| Amount | raw `amount` POST field ([`_compute_amount`](../../apps/app_operation/views/create_operation/base.py:52)); validated > 0 at model; never balance-gated | raw `amount` POST field ([`_compute_amount`](../../apps/app_operation/views/create_operation/base.py:52)); validated > 0 at model; never balance-gated |
| POST parsing | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) — date format, description, category (n/a), `amount_paid` (n/a, forced 0) | same |
| List entry | **no standard dropdown entry** in [`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html) — admin-only routes | same |
| Detail | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) — shows both transactions + settlement + reversal button | same |
| Reverse | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (CC24/CC25) | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) — same guards (CD24/CD25) |

---

## 9. Branch catalog (all possible branches)

**Correction Credit — create validation:** CC1 source=system · CC2 dest=project · CC3 source active · CC4 dest active · CC5 source fund active · CC6 target fund active · CC7 amount>0 · CC8 officer staff · CC9 officer active · CC10 not closed-period · CC11 covering period exists · CC12 balance exempt · CC13 tx entity-type · CC14 tx op-type · CC15 no category

**Correction Credit — create effects:** CC16 issuance tx · CC17 payment tx · CC18 direction system→project · CC19 settled immediately · CC20 project ▲ · CC21 system (virtual) ▼ · CC22 no invoice/movements · CC23 period assigned

**Correction Credit — reverse validation:** CC24 not reversed · CC25 not a reversal · CC26 no explicit txs · CC27 no adjustments (n/a) · CC28 reason required (view)

**Correction Credit — reverse effects:** CC29 reversal record · CC30 original reversed · CC31 identity copied · CC32 issuance counter-tx · CC33 payment counter-tx · CC34 type preserved · CC35 reversal owns no txs · CC36 project restored · CC37 settlement cleared · CC38 reason in description · CC39 differential invariant

**Correction Debit — create validation:** CD1 source=project · CD2 dest=system · CD3 source active · CD4 dest active · CD5 source fund active · CD6 target fund active · CD7 amount>0 · CD8 officer staff · CD9 officer active · CD10 not closed-period · CD11 covering period exists · CD12 balance exempt (may go into deficit) · CD13 tx entity-type · CD14 tx op-type · CD15 no category

**Correction Debit — create effects:** CD16 issuance tx · CD17 payment tx · CD18 direction project→system · CD19 settled immediately · CD20 project ▼ · CD21 system (virtual) ▲ · CD22 no invoice/movements · CD23 period assigned

**Correction Debit — reverse validation:** CD24 not reversed · CD25 not a reversal · CD26 no explicit txs · CD27 no adjustments (n/a) · CD28 reason required (view)

**Correction Debit — reverse effects:** CD29 reversal record · CD30 original reversed · CD31 identity copied · CD32 issuance counter-tx · CD33 payment counter-tx · CD34 type preserved · CD35 reversal owns no txs · CD36 project restored · CD37 settlement cleared · CD38 reason in description · CD39 differential invariant

**pay / immutability (both):** BP1 `process_payment` no-op · BP2 `create_payment_transaction` blocked after create · IM1/IM2/IM3 source/destination/amount immutable

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| CC Tx creation + counts | [`test_creates_issuance_and_payment_transactions`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:78) | CC16, CC17 |
| CC Tx direction | [`test_transaction_funds_are_correct`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:91) | CC18 |
| CC Settlement | [`test_is_fully_settled_after_creation`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:99) | CC19 |
| CC Project ▲ | [`test_project_fund_increases_by_correction_amount`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:107) | CC20 |
| CC No category | [`test_no_category_config`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:119) | CC15 |
| CC Source/dest validation | [`test_source_must_be_system_entity`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:127), [`test_source_world_entity_raises_validation_error`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:133), [`test_destination_must_be_project_entity`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:159) | CC1, CC2 |
| CC Active entities | [`test_source_must_be_active`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:139), [`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:147), [`test_destination_must_be_active`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:165) | CC3–CC6 |
| CC Amount/officer | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:177), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:182), [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:190), [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:198) | CC7–CC9 |
| CC Immutability | [`test_source_is_immutable`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:210), [`test_destination_is_immutable`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:219), [`test_amount_is_immutable`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:228) | IM1–IM3 |
| CC One-shot / balance | [`test_can_pay_is_false`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:240), [`test_one_shot_prevents_second_payment`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:243), [`test_check_balance_on_payment_is_disabled`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py:258) | BP1, BP2, CC12 |
| CC Reverse happy path | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:75), [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:81), [`test_reversal_is_reversal`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:88), [`test_reversal_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:94) | CC29–CC31 |
| CC Counter txs | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:101), [`test_reverse_counter_transactions_flip_funds`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:110), [`test_reverse_counter_transactions_preserve_type`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:120) | CC32–CC35 |
| CC Project restored | [`test_project_fund_restored_after_reversal`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:127) | CC36 |
| CC Differential invariant | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:141) | CC39, CC37, CC21 |
| CC Reverse constraints | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:162), [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py:169) | CC24, CC25 |
| CD Tx creation + counts | [`test_creates_issuance_and_payment_transactions`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:86) | CD16, CD17 |
| CD Tx direction | [`test_transaction_funds_are_correct`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:99) | CD18 |
| CD Settlement | [`test_is_fully_settled_after_creation`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:107) | CD19 |
| CD Project ▼ | [`test_project_fund_decreases_by_correction_amount`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:115) | CD20 |
| CD No category | [`test_no_category_config`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:128) | CD15 |
| CD Source/dest validation | [`test_source_must_be_project_entity`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:136), [`test_source_system_entity_raises_validation_error`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:142), [`test_destination_must_be_system_entity`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:167), [`test_destination_world_entity_raises_validation_error`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:173) | CD1, CD2 |
| CD Active entities | [`test_source_must_be_active`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:147), [`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:155), [`test_destination_must_be_active`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:179) | CD3–CD6 |
| CD Amount/officer | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:191), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:196), [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:205), [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:213) | CD7–CD9 |
| CD Immutability | [`test_source_is_immutable`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:225), [`test_destination_is_immutable`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:237), [`test_amount_is_immutable`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:246) | IM1–IM3 |
| CD Balance exempt | [`test_check_balance_on_payment_is_disabled`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:258), [`test_debit_succeeds_even_with_insufficient_balance`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:262) | CD12 |
| CD One-shot / can_pay | [`test_can_pay_is_false`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:274), [`test_one_shot_prevents_second_payment`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py:277) | BP1, BP2 |
| CD Reverse happy path | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:82), [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:88), [`test_reversal_is_reversal`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:95), [`test_reversal_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:101) | CD29–CD31 |
| CD Counter txs | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:108), [`test_reverse_counter_transactions_flip_funds`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:117), [`test_reverse_counter_transactions_preserve_type`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:127) | CD32–CD35 |
| CD Project restored | [`test_project_fund_restored_after_reversal`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:134) | CD36 |
| CD Differential invariant | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:148) | CD39, CD37, CD21 |
| CD Reverse constraints | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:169), [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py:176) | CD24, CD25 |

---

## 11. Tasks

- [x] Verify both issuance + payment transactions are created on save (CC16/CC17 and CD16/CD17)
- [x] Verify transaction fund direction — Credit `system.fund → project.fund`, Debit `project.fund → system.fund`
- [x] Verify operation is fully settled immediately
- [x] Verify all validation branches (CC1–CC15 and CD1–CD15)
- [x] Verify `check_balance_on_payment=False` — Credit balance exempt (system), Debit may go into deficit
- [x] Verify `has_category=False` and `category_required=False` class-level config
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `can_pay=False` — `create_payment_transaction()` is blocked after creation
- [x] Verify reversal creates counter-transactions — Credit `project.fund → system.fund`, Debit `system.fund → project.fund`
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify reversal is marked as `is_reversal=True` and inherits amount/source/destination
- [x] Verify counter-transactions preserve transaction type
- [x] Verify project fund restored after reversal (both variants)
- [x] Verify cannot reverse an already-reversed operation or a reversal
- [x] UI: create form — Credit source locked to System / destination = project from URL; Debit source = project from URL / destination locked to System
- [x] UI: operation detail shows both transactions and reversal button
- [ ] Add dedicated focused `test_reversal_clears_settlement_state` for both Correction variants (CC37/CD37 pinned only by the differential invariant)
- [ ] Add dedicated focused `test_reason_flows_to_reversal_description` for both Correction variants (CC38/CD38 pinned only by the shared engine)
