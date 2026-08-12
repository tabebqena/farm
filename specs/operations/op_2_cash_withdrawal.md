# Cash Withdrawal — Operation Contract

**Epic:** 8.2 — Cash Operations
**Type:** One-shot, auto-settled
**Actions:** `create`, `reverse`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Cash Withdrawal** operation.
> Every clause below is registered to its implementing code (model → mixin → transaction → view) and to its pinning test.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> Other operations follow the same structure — see [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md).

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.CASH_WITHDRAWAL` (`"CASH_WITHDRAWAL"`) | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:6) |
| Proxy class | `CashWithdrawalOperation` | [`op_cash_withdrawal.py`](../../apps/app_operation/models/proxies/op_cash_withdrawal.py:7) |
| URL slug | `"cash-withdrawal"` | [`op_cash_withdrawal.py`](../../apps/app_operation/models/proxies/op_cash_withdrawal.py:11) |
| Label | `"Cash Withdrawal"` | [`op_cash_withdrawal.py`](../../apps/app_operation/models/proxies/op_cash_withdrawal.py:12) |
| Theme | `danger` / `bi-box-arrow-up-right` (inherited default — not overridden) | [`operation.py`](../../apps/app_operation/models/operation.py:112) |
| Source role | `url` (must be a Person) | [`op_cash_withdrawal.py`](../../apps/app_operation/models/proxies/op_cash_withdrawal.py:13) |
| Destination role | `world` | [`op_cash_withdrawal.py`](../../apps/app_operation/models/proxies/op_cash_withdrawal.py:14) |
| Registered in | `PROXY_MAP` | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:28) |
| Cross-op reference | row CW | [`operations-comparison.md`](operations-comparison.md) |

**Configuration flags** (all on [`op_cash_withdrawal.py`](../../apps/app_operation/models/proxies/op_cash_withdrawal.py:7)):

| Flag | Value | Meaning |
|------|-------|---------|
| `_issuance_transaction_type` | `CAPITAL_WITHDRAWAL_ISSUANCE` | issuance tx created on save |
| `_payment_transaction_type` | `CAPITAL_WITHDRAWAL_PAYMENT` | payment tx created on save (one-shot) |
| `_is_one_shot_operation` | `True` | payment fires at create; no standalone pay action |
| `can_pay` | `False` | `process_payment()` is a no-op |
| `is_partially_payable` | `False` | payment must equal amount (one-shot) |
| `max_payment_transaction_count` | `1` | exactly one payment tx ever |
| `check_balance_on_payment` | `True` | payer (person) fund is balance-checked before the payment tx |
| `has_category` / `category_required` | `False` | no financial category |
| `has_repayment` | `False` | no repayment action |
| `has_invoice` | `False` | no invoice items / no inventory movements |

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row links the clause to the code that must honor it.

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_source`/`clean_destination` | [`op_cash_withdrawal.py`](../../apps/app_operation/models/proxies/op_cash_withdrawal.py:7) |
| Proxy registry / URL→class resolution | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:28) |
| Shared `Operation` engine (`clean`, `save`, `reverse`, `create`, `resolve_request`, period assignment, reversable tx types) | [`operation.py`](../../apps/app_operation/models/operation.py:34) |
| Operation type enum | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:6) |

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
| Payer balance check before payment tx (`check_balance_on_payment=True` → `can_pay`) | [`LinkedPaymentTransactionMixin.create_payment_transaction()`](../../apps/app_base/mixins.py:377) |
| One-shot guard (single payment, amount == op.amount) | [`LinkedPaymentTransactionMixin.create_payment_transaction()`](../../apps/app_base/mixins.py:391) |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | [`ReversableModel`](../../apps/app_base/models.py:133) + [`Operation.reverse()`](../../apps/app_operation/models/operation.py:997) |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | [`models.py`](../../apps/app_transaction/models.py:33) |
| `CAPITAL_WITHDRAWAL_ISSUANCE` (person → world) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:150), entity map [:519](../../apps/app_transaction/transaction_type.py:519), op map [:609](../../apps/app_transaction/transaction_type.py:609) |
| `CAPITAL_WITHDRAWAL_PAYMENT` (person → world, affects balance) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:160), entity map [:520](../../apps/app_transaction/transaction_type.py:520), op map [:610](../../apps/app_transaction/transaction_type.py:610), payment set [:428](../../apps/app_transaction/transaction_type.py:428) |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Person balance = incoming payment txs − outgoing payment txs | [`Entity.balance`](../../apps/app_entity/models/__init__.py:668) → [`balance_at`](../../apps/app_entity/models/__init__.py:414) |
| Balance enforcement: `can_pay` only balance-checks real (non-virtual) internal funds | [`Entity.can_pay`](../../apps/app_entity/models/__init__.py:704) |
| Open financial period auto-created on entity creation | [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (generic, resolves URL person source + World destination) | [`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:75) |
| POST parsing/validation | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) |
| Reverse view (reason required) | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) |
| Detail view (transactions + reversal button) | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) |
| URL: `/<pk>/<op_type>/create` | [`urls.py`](../../apps/app_operation/urls.py:142) |
| URL: `/<pk>/reverse/` | [`urls.py`](../../apps/app_operation/urls.py:192) |
| URL: `/<pk>/detail/` | [`urls.py`](../../apps/app_operation/urls.py:182) |
| Templates | [`generic_form.html`](../../apps/app_operation/templates/app_operation/generic_form.html), [`reverse_form.html`](../../apps/app_operation/templates/app_operation/reverse_form.html), [`operation_detail.html`](../../apps/app_operation/templates/app_operation/operation_detail.html), entry link in [`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html:24) |

### 2.6 Tests

| Concern | Test file |
|---------|-----------|
| Create branches | [`test_cash_withdrawal_cash_withdrawal_create.py`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py) |
| Reverse branches | [`test_cash_withdrawal_cash_withdrawal_reversal.py`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py) |
| Coverage manifest (executable branch registry) | [`tests/base.py`](../../apps/app_operation/tests/base.py:711) |

---

## 3. Money flow & entities

- **Source (payer):** the **Person** entity in the URL (`is_person=True`). Its fund is the source fund and is **balance-checked** — the withdrawer's real internal fund must cover `amount` (VC12).
- **Destination (receiver):** the single **World** entity (`is_world=True`). Virtual — never balance-checked, exempt from period checks (world has no periods).
- **Transaction flow** (both on create, person → world):

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `CAPITAL_WITHDRAWAL_ISSUANCE` | `person.fund → world.fund` | none (issuance, not a payment type) |
| 2 | `CAPITAL_WITHDRAWAL_PAYMENT` | `person.fund → world.fund` | ▼ person fund by `amount` |

- **Payment source fund:** `self.source` (person) — [`op_cash_withdrawal.py`](../../apps/app_operation/models/proxies/op_cash_withdrawal.py:29)
- **Payment target fund:** `self.destination` (world) — [`op_cash_withdrawal.py`](../../apps/app_operation/models/proxies/op_cash_withdrawal.py:33)

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

Entry points: model `CashWithdrawalOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx, then payment tx).

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source is Person | `source.is_person` | `ValidationError` | `"Cash Withdrawal source must be a Person entity."` | [`clean_source`](../../apps/app_operation/models/proxies/op_cash_withdrawal.py:37) | [`test_source_must_be_person_entity`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:118) |
| VC2 | Destination is World | `destination.is_world` | `ValidationError` | `"Cash Withdrawal destination must be the World entity."` | [`clean_destination`](../../apps/app_operation/models/proxies/op_cash_withdrawal.py:41) | [`test_destination_must_be_world_entity`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:123) |
| VC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | [`test_source_entity_must_be_active`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:130) |
| VC4 | Destination entity active | `destination.active` | `ValidationError` | same as VC3 | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | [`test_destination_entity_must_be_active`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:138) |
| VC5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | [`SourceFundMixin`](../../apps/app_base/mixins.py:132) | merged with VC3 ([`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:146)) |
| VC6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | [`TargetFundMixin`](../../apps/app_base/mixins.py:152) | merged with VC4 (world is always active) |
| VC7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | [`AmountCleanMixin`](../../apps/app_base/mixins.py:69) | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:158), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:163) |
| VC8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:81) | [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:172) |
| VC9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:84) | [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:180) |
| VC10 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:541) | covered by the shared period suite (see §10) |
| VC11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) | covered by the shared period suite (see §10) |
| VC12 | Balance checked (person payer) | `payment_source_fund.can_pay(amount)` | `ValidationError` | `"Insufficient funds: fund balance (%(balance)s) is less than the payment amount (%(amount)s)."` | `check_balance_on_payment=True` → [`LinkedPaymentTransactionMixin.create_payment_transaction()`](../../apps/app_base/mixins.py:377) → [`Entity.can_pay`](../../apps/app_entity/models/__init__.py:704) | [`test_check_balance_on_payment_is_enabled`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:272), [`test_insufficient_funds_blocked`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:276), [`test_withdrawal_without_sufficient_funds_raises_error`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:291), [`test_withdrawal_exceeding_balance_raises_error`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:302) |
| VC13 | Tx entity-type contract | `source.is_person` and `target.is_world` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | [`Transaction.create()`](../../apps/app_transaction/models.py:144) + map [:519](../../apps/app_transaction/transaction_type.py:519) | implied by VC1/VC2 (model clean blocks first) |
| VC14 | Tx operation-type allowed | document is `CASH_WITHDRAWAL` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | [`Transaction.create()`](../../apps/app_transaction/models.py:155) + map [:609](../../apps/app_transaction/transaction_type.py:609) | implied by VC1/VC2 |
| VC15 | Source ≠ target | person ≠ world | always true | `"Source and target funds must be different."` | [`Transaction.clean()`](../../apps/app_transaction/models.py:107) | structural (person ≠ world) |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | 1 × `CAPITAL_WITHDRAWAL_ISSUANCE`, amount `== op.amount`, `person → world` | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:222) | [`test_creates_issuance_and_payment_transactions`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:67) |
| SC2 | Payment tx created | 1 × `CAPITAL_WITHDRAWAL_PAYMENT`, amount `== op.amount`, `person → world` | [`LinkedPaymentTransactionMixin.save()`](../../apps/app_base/mixins.py:424) | same as SC1 |
| SC3 | Tx amounts equal op amount | both txs `amount == op.amount` | transaction creation | [`test_transaction_amounts_match_operation`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:84) |
| SC4 | Tx fund direction | both txs `source=person`, `target=world` | [`op_cash_withdrawal.py`](../../apps/app_operation/models/proxies/op_cash_withdrawal.py:29) | [`test_transaction_funds_are_correct`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:91) |
| SC5 | Fully settled immediately | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:268) | [`test_is_fully_settled_after_creation`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:106) |
| SC6 | Person fund ▼ amount | `person.balance` decreases by `amount` | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) | [`test_withdrawer_balance_decreases_after_withdrawal`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:239) |
| SC7 | World (virtual) ▲ | world balance moves but is never enforced / never read for checks | `can_pay` virtual exemption | differential invariant ([`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:150)) |
| SC8 | No invoice / no movements | `has_invoice=False`; no invoice items; no movement lines | `has_invoice=False` | config flag (`has_invoice=False`); no ledger/movement machinery in `post_save_tasks` |
| SC9 | Period auto-assigned | `period` = the withdrawer's covering period (open period auto-created at entity creation) | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) + [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) | covered by shared period suite |

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:34) | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:119) |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:47) | [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:126) |
| VR3 | No explicit txs to reverse | all txs are implicit (one-shot issuance + payment) | `ValidationError` (would require manual reversal) | `"You can't reverse this object as it has non-reversed transactions…"` | [`ReversableModel._requires_transaction_reversal`](../../apps/app_base/models.py:203) + [`Operation._implicit_reversable_transaction_types`](../../apps/app_operation/models/operation.py:478) | implied by successful reverse ([`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:86)) |
| VR4 | No non-reversed adjustments | n/a — Cash Withdrawal is not adjustable | never fails | — | `is_adjustable=False` | n/a |
| VR5 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:82) | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:235) | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:60) |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:270) | [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:66) |
| SR3 | Reversal inherits identity | `amount`, `source`, `destination` copied | [`ReversableModel._get_reverse_kwargs`](../../apps/app_base/models.py:184) | [`test_reverse_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:79) |
| SR4 | Counter-tx for issuance | `world → person`, same amount, same type, `reversal_of=original` | [`Transaction.reverse()`](../../apps/app_transaction/models.py:206) | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:86) |
| SR5 | Counter-tx for payment | `world → person`, same amount, same type, `reversal_of=original` | same as SR4 | [`test_reverse_counter_transactions_flip_funds`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:98) |
| SR6 | Counter-txs preserve type + amount | `counter.type == original.type`, `counter.amount == original.amount` | same as SR4 | [`test_reverse_counter_transactions_preserve_type`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:108) |
| SR7 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:226) | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:92) |
| SR8 | Person fund restored | `person.balance` back to pre-create baseline | `balance_at` | [`test_withdrawer_balance_restored_after_reversal`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:136) |
| SR9 | Settlement state cleared | `amount_settled == 0`, `is_fully_settled == False` | `amount_settled` | differential invariant ([`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:150)); no dedicated focused test yet (see §11) |
| SR10 | Reason flows to reversal | `reversal.description` contains the reason | [`ReversableModel.reverse()`](../../apps/app_base/models.py:262) | shared engine (see §11 — no dedicated focused test yet) |
| SR11 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger) | whole engine | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:150) |

### 5.3 `pay` (one-shot guard)

There is **no standalone pay action** for Cash Withdrawal:

| Branch | Behavior | Enforced by | Pinned by test |
|--------|----------|-------------|----------------|
| `process_payment()` called | no-op (returns immediately — `can_pay=False`) | [`process_payment`](../../apps/app_operation/models/operation.py:686) | n/a (covered by `can_pay=False`) |
| `create_payment_transaction()` called after create | `ValidationError` — one-shot allows a single payment only, amount must equal `op.amount` (balance re-checked first, VC12) | [`create_payment_transaction`](../../apps/app_base/mixins.py:391) | [`test_one_shot_prevents_second_payment`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:224) |

### 5.4 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by [`ImmutableMixin`](../../apps/app_base/mixins.py:30) via `_immutable_fields` ([`operation.py`](../../apps/app_operation/models/operation.py:51)).

| Branch | Enforced by | Pinned by test |
|--------|-------------|----------------|
| `source` changed after save | `ImmutableMixin.save()` | [`test_source_is_immutable`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:192) |
| `destination` changed after save | `ImmutableMixin.save()` | [`test_destination_is_immutable`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:203) |
| `amount` changed after save | `ImmutableMixin.save()` | [`test_amount_is_immutable`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:212) |

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — [`Entity.save()`](../../apps/app_entity/models/__init__.py:714).
- The operation's governing entity (`period_entity`) is the **source person** (`_source_role = "url"`) — [`Operation.period_entity`](../../apps/app_operation/models/operation.py:498).
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC11).
- New operations dated inside a **closed** period are rejected (VC10) — [`is_date_in_closed_period`](../../apps/app_operation/models/period.py:14).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period ([`_reverse_period`](../../apps/app_operation/models/operation.py:455)).

---

## 7. Entity roles & balance contract

- Person is the only allowed source; world the only allowed destination — enforced at model (VC1/VC2) and transaction (VC13) layers.
- `person.balance` is derived exclusively from **payment-type** transactions (`balance_at`); the issuance tx never moves a balance.
- The withdrawer's fund is a **real internal fund** and is balance-checked on payment creation (`check_balance_on_payment=True`, VC12). `can_pay` only balance-checks real (non-virtual) internal funds; the world destination is virtual and never checked.
- Cash Withdrawal is the exact mirror of Cash Injection (CI): CI moves `world → person` with no balance check (world exempt), CW moves `person → world` with a balance check (person pays).

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Create route | `POST/GET /<person_pk>/cash-withdrawal/create` → [`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:75) |
| Source selection | the **Person** from the URL (`_source_role="url"`, resolved by [`resolve_request`](../../apps/app_operation/models/operation.py:202)); no picker |
| Destination selection | locked to the single **World** entity (`_dest_role="world"`); [`get_related_entities`](../../apps/app_operation/models/operation.py:440) returns `[]` → no secondary-entity field |
| Category | hidden (no category) |
| Amount | raw `amount` POST field ([`_compute_amount`](../../apps/app_operation/views/create_operation/base.py:52)); validated > 0 at model; balance-checked at payment (VC12) |
| POST parsing | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) — date format, description, category (n/a), `amount_paid` (n/a, forced 0) |
| List entry | "Cash Withdrawal" link in [`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html:24) |
| Detail | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) — shows both transactions + settlement + reversal button |
| Reverse | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source=person · VC2 dest=world · VC3 source active · VC4 dest active · VC5 source fund active · VC6 target fund active · VC7 amount>0 · VC8 officer staff · VC9 officer active · VC10 not closed-period · VC11 covering period exists · VC12 balance checked · VC13 tx entity-type · VC14 tx op-type · VC15 source≠target

**create — effects:** SC1 issuance tx · SC2 payment tx · SC3 amounts equal · SC4 direction person→world · SC5 settled immediately · SC6 person ▼ · SC7 world (virtual) ▲ · SC8 no invoice/movements · SC9 period assigned

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no explicit txs · VR4 no adjustments (n/a) · VR5 reason required (view)

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 identity copied · SR4 issuance counter-tx · SR5 payment counter-tx · SR6 type/amount preserved · SR7 reversal owns no txs · SR8 person restored · SR9 settlement cleared · SR10 reason in description · SR11 differential invariant

**pay / immutability:** BP1 `process_payment` no-op · BP2 `create_payment_transaction` blocked after create · IM1/IM2/IM3 source/destination/amount immutable

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| Tx creation + counts | [`test_creates_issuance_and_payment_transactions`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:67) | SC1, SC2 |
| Tx amounts | [`test_transaction_amounts_match_operation`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:84) | SC3 |
| Tx direction | [`test_transaction_funds_are_correct`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:91) | SC4 |
| Settlement | [`test_is_fully_settled_after_creation`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:106) | SC5 |
| Source/dest validation | [`test_source_must_be_person_entity`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:118), [`test_destination_must_be_world_entity`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:123) | VC1, VC2 |
| Active entities | [`test_source_entity_must_be_active`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:130), [`test_destination_entity_must_be_active`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:138), [`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:146) | VC3–VC6 |
| Amount | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:158), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:163) | VC7 |
| Officer | [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:172), [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:180) | VC8, VC9 |
| Immutability | [`test_source_is_immutable`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:192), [`test_destination_is_immutable`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:203), [`test_amount_is_immutable`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:212) | IM1–IM3 |
| One-shot guard | [`test_one_shot_prevents_second_payment`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:224) | BP2 |
| Person balance ▼ | [`test_withdrawer_balance_decreases_after_withdrawal`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:239), [`test_injection_then_withdrawal_succeeds`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:254) | SC6 |
| Balance check enabled | [`test_check_balance_on_payment_is_enabled`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:272) | VC12 |
| Insufficient funds | [`test_insufficient_funds_blocked`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:276), [`test_withdrawal_without_sufficient_funds_raises_error`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:291), [`test_withdrawal_exceeding_balance_raises_error`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_create.py:302) | VC12 |
| Closed / covering period | shared period suite (VC10/VC11 enforced by [`Operation.clean()`](../../apps/app_operation/models/operation.py:541) / [`Operation.save()`](../../apps/app_operation/models/operation.py:595)) | VC10, VC11, SC9 |
| Reverse happy path | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:60), [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:66), [`test_reversal_is_reversal`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:73), [`test_reverse_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:79) | SR1–SR3 |
| Counter txs | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:86), [`test_reverse_counter_transactions_flip_funds`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:98), [`test_reverse_counter_transactions_preserve_type`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:108) | SR4–SR7 |
| Reverse constraints | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:119), [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:126) | VR1, VR2 |
| Person balance restored | [`test_withdrawer_balance_restored_after_reversal`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:136) | SR8 |
| Differential invariant | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/cash/test_cash_withdrawal_cash_withdrawal_reversal.py:150) | SR11, SC7, SR9 |

---

## 11. Tasks

- [x] Verify both `CAPITAL_WITHDRAWAL_ISSUANCE` and `CAPITAL_WITHDRAWAL_PAYMENT` are created on save
- [x] Verify transaction fund direction: `person.fund → world.fund` for both
- [x] Verify operation is fully settled immediately
- [x] Verify all validation branches VC1–VC15 (including the balance check — VC12)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `create_payment_transaction()` is blocked after creation (one-shot)
- [x] Verify reversal creates counter-transactions: `world.fund → person.fund`
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify counter-transactions preserve transaction type
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [x] Verify person balance affected correctly by create (▼ amount)
- [x] Verify person balance restored by reverse
- [x] UI: create form — source = person from URL, destination locked to World
- [x] UI: operation detail shows both transactions and reversal button
- [x] Add focused `test_check_balance_on_payment_is_enabled` / `test_insufficient_funds_blocked` pinning VC12
- [ ] Add a dedicated focused `test_reversal_clears_settlement_state` for Cash Withdrawal (SR9 currently pinned only by the differential invariant)
- [ ] Add a dedicated focused `test_reason_flows_to_reversal_description` for Cash Withdrawal (SR10 currently pinned only by the shared engine)
