# Cash Injection — Operation Contract

**Epic:** 8.1 — Cash Operations
**Type:** One-shot, auto-settled
**Actions:** `create`, `reverse`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Cash Injection** operation.
> Every clause below is registered to its implementing code (model → mixin → transaction → view) and to its pinning test.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> Other operations follow the same structure — see [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md).

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.CASH_INJECTION` (`"CASH_INJECTION"`) | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:5) |
| Proxy class | `CashInjectionOperation` | [`op_cash_injection.py`](../../apps/app_operation/models/proxies/op_cash_injection.py:7) |
| URL slug | `"cash-injection"` | [`op_cash_injection.py`](../../apps/app_operation/models/proxies/op_cash_injection.py:11) |
| Label | `"Cash Injection"` | [`op_cash_injection.py`](../../apps/app_operation/models/proxies/op_cash_injection.py:12) |
| Theme | `success` / `bi-box-arrow-in-down` | [`op_cash_injection.py`](../../apps/app_operation/models/proxies/op_cash_injection.py:22) |
| Source role | `world` | [`op_cash_injection.py`](../../apps/app_operation/models/proxies/op_cash_injection.py:13) |
| Destination role | `url` (must be a Person) | [`op_cash_injection.py`](../../apps/app_operation/models/proxies/op_cash_injection.py:14) |
| Registered in | `PROXY_MAP` | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:26) |
| Cross-op reference | row CI | [`operations-comparison.md`](operations-comparison.md) |

**Configuration flags** (all on [`op_cash_injection.py`](../../apps/app_operation/models/proxies/op_cash_injection.py:7)):

| Flag | Value | Meaning |
|------|-------|---------|
| `_issuance_transaction_type` | `CASH_INJECTION_ISSUANCE` | issuance tx created on save |
| `_payment_transaction_type` | `CASH_INJECTION_PAYMENT` | payment tx created on save (one-shot) |
| `_is_one_shot_operation` | `True` | payment fires at create; no standalone pay action |
| `can_pay` | `False` | `process_payment()` is a no-op |
| `is_partially_payable` | `False` | payment must equal amount (one-shot) |
| `max_payment_transaction_count` | `1` | exactly one payment tx ever |
| `has_category` / `category_required` | `False` | no financial category |
| `has_repayment` | `False` | no repayment action |
| `has_invoice` | `False` | no invoice items / no inventory movements |

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row links the clause to the code that must honor it.

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_source`/`clean_destination` | [`op_cash_injection.py`](../../apps/app_operation/models/proxies/op_cash_injection.py:7) |
| Proxy registry / URL→class resolution | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:26) |
| Shared `Operation` engine (`clean`, `save`, `reverse`, `create`, `resolve_request`, period assignment, reversable tx types) | [`operation.py`](../../apps/app_operation/models/operation.py:34) |
| Operation type enum | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:5) |

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
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | [`ReversableModel`](../../apps/app_base/models.py:133) + [`Operation.reverse()`](../../apps/app_operation/models/operation.py:997) |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | [`models.py`](../../apps/app_transaction/models.py:33) |
| `CASH_INJECTION_ISSUANCE` (world → person) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:136), entity map [:516](../../apps/app_transaction/transaction_type.py:516), op map [:607](../../apps/app_transaction/transaction_type.py:607) |
| `CASH_INJECTION_PAYMENT` (world → person, affects balance) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:143), entity map [:517](../../apps/app_transaction/transaction_type.py:517), op map [:608](../../apps/app_transaction/transaction_type.py:608), payment set [:427](../../apps/app_transaction/transaction_type.py:427) |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Person balance = incoming payment txs − outgoing payment txs | [`Entity.balance`](../../apps/app_entity/models/__init__.py:668) → [`balance_at`](../../apps/app_entity/models/__init__.py:414) |
| World (virtual) never balance-checked | [`Entity.can_pay`](../../apps/app_entity/models/__init__.py:704) |
| Open financial period auto-created on entity creation | [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (generic, resolves world source + URL person destination) | [`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:75) |
| POST parsing/validation | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) |
| Reverse view (reason required) | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) |
| Detail view (transactions + reversal button) | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) |
| URL: `/<pk>/<op_type>/create` | [`urls.py`](../../apps/app_operation/urls.py:142) |
| URL: `/<pk>/reverse/` | [`urls.py`](../../apps/app_operation/urls.py:192) |
| URL: `/<pk>/detail/` | [`urls.py`](../../apps/app_operation/urls.py:182) |
| Templates | [`generic_form.html`](../../apps/app_operation/templates/app_operation/generic_form.html), [`reverse_form.html`](../../apps/app_operation/templates/app_operation/reverse_form.html), [`operation_detail.html`](../../apps/app_operation/templates/app_operation/operation_detail.html), entry link in [`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html:18) |

### 2.6 Tests

| Concern | Test file |
|---------|-----------|
| Create branches | [`test_cash_injection_cash_injection_create.py`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py) |
| Reverse branches | [`test_cash_injection_cash_injection_reversal.py`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py) |
| Coverage manifest (executable branch registry) | [`tests/base.py`](../../apps/app_operation/tests/base.py:670) |

---

## 3. Money flow & entities

- **Source (payer):** the single **World** entity (`is_world=True`). Virtual — never balance-checked, exempt from period checks (world has no periods).
- **Destination (receiver):** the **Person** entity in the URL (`is_person=True`). Its fund is the target fund.
- **Transaction flow** (both on create, world → person):

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `CASH_INJECTION_ISSUANCE` | `world.fund → person.fund` | none (issuance, not a payment type) |
| 2 | `CASH_INJECTION_PAYMENT` | `world.fund → person.fund` | ▲ person fund by `amount` |

- **Payment source fund:** `self.source` (world) — [`op_cash_injection.py`](../../apps/app_operation/models/proxies/op_cash_injection.py:30)
- **Payment target fund:** `self.destination` (person) — [`op_cash_injection.py`](../../apps/app_operation/models/proxies/op_cash_injection.py:34)

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

Entry points: model `CashInjectionOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx, then payment tx).

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source is World | `source.is_world` | `ValidationError` | `"Cash Injection source must be the World entity."` | [`clean_source`](../../apps/app_operation/models/proxies/op_cash_injection.py:37) | [`test_source_must_be_world`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:98) |
| VC2 | Destination is Person | `destination.is_person` | `ValidationError` | `"Cash Injection must target a Person entity."` | [`clean_destination`](../../apps/app_operation/models/proxies/op_cash_injection.py:41) | [`test_destination_must_be_person_entity`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:105) |
| VC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | [`test_source_entity_must_be_active`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:112) |
| VC4 | Destination entity active | `destination.active` | `ValidationError` | same as VC3 | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | [`test_destination_entity_must_be_active`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:120) |
| VC5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | [`SourceFundMixin`](../../apps/app_base/mixins.py:132) | merged with VC3 ([`test_source_entity_must_be_able_to_pay`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:128)) |
| VC6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | [`TargetFundMixin`](../../apps/app_base/mixins.py:152) | merged with VC4 |
| VC7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | [`AmountCleanMixin`](../../apps/app_base/mixins.py:69) | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:140), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:145) |
| VC8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:81) | [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:154) |
| VC9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:84) | [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:162) |
| VC10 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:541) | [`test_operation_blocked_when_destination_in_closed_period`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:248) |
| VC11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) | [`test_operation_blocked_when_no_covering_period`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:264) |
| VC12 | Balance exempt (world payer) | no balance check | never fails | — | `check_balance_on_payment=False` (default) | [`test_check_balance_on_payment_is_disabled`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:219), [`test_injection_succeeds_regardless_of_prior_injections`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:223) |
| VC13 | Tx entity-type contract | `source.is_world` and `target.is_person` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | [`Transaction.create()`](../../apps/app_transaction/models.py:144) + map [:516](../../apps/app_transaction/transaction_type.py:516) | implied by VC1/VC2 (model clean blocks first) |
| VC14 | Tx operation-type allowed | document is `CASH_INJECTION` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | [`Transaction.create()`](../../apps/app_transaction/models.py:155) + map [:607](../../apps/app_transaction/transaction_type.py:607) | implied by VC1/VC2 |
| VC15 | Source ≠ target | world ≠ person | always true | `"Source and target funds must be different."` | [`Transaction.clean()`](../../apps/app_transaction/models.py:107) | structural (world ≠ person) |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | 1 × `CASH_INJECTION_ISSUANCE`, amount `== op.amount`, `world → person` | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:222) | [`test_creates_issuance_and_payment_transactions`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:47) |
| SC2 | Payment tx created | 1 × `CASH_INJECTION_PAYMENT`, amount `== op.amount`, `world → person` | [`LinkedPaymentTransactionMixin.save()`](../../apps/app_base/mixins.py:424) | same as SC1 |
| SC3 | Tx amounts equal op amount | both txs `amount == op.amount` | transaction creation | [`test_transaction_amounts_match_operation`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:64) |
| SC4 | Tx fund direction | both txs `source=world`, `target=person` | [`op_cash_injection.py`](../../apps/app_operation/models/proxies/op_cash_injection.py:30) | [`test_transaction_funds_are_correct`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:71) |
| SC5 | Fully settled immediately | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:268) | [`test_is_fully_settled_after_creation`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:86) |
| SC6 | Person fund ▲ amount | `person.balance` increases by `amount` | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) | [`test_receiver_balance_increases_after_cash_injection`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:233) |
| SC7 | World (virtual) ▼ | world balance moves but is never enforced / never read for checks | `can_pay` virtual exemption | differential invariant ([`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:138)) |
| SC8 | No invoice / no movements | `has_invoice=False`; no invoice items; no movement lines | `has_invoice=False` | [`test_no_invoice_items_and_no_movements`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:278) |
| SC9 | Period auto-assigned | `period` = the person's covering period (open period auto-created at entity creation) | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) + [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) | covered by period suite |

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:34) | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:107) |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:47) | [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:114) |
| VR3 | No explicit txs to reverse | all txs are implicit (one-shot issuance + payment) | `ValidationError` (would require manual reversal) | `"You can't reverse this object as it has non-reversed transactions…"` | [`ReversableModel._requires_transaction_reversal`](../../apps/app_base/models.py:203) + [`Operation._implicit_reversable_transaction_types`](../../apps/app_operation/models/operation.py:478) | implied by successful reverse ([`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:72)) |
| VR4 | No non-reversed adjustments | n/a — Cash Injection is not adjustable | never fails | — | `is_adjustable=False` | n/a |
| VR5 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:82) | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:235) | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:46) |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:270) | [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:52) |
| SR3 | Reversal inherits identity | `amount`, `source`, `destination` copied | [`ReversableModel._get_reverse_kwargs`](../../apps/app_base/models.py:184) | [`test_reverse_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:65) |
| SR4 | Counter-tx for issuance | `person → world`, same amount, same type, `reversal_of=original` | [`Transaction.reverse()`](../../apps/app_transaction/models.py:206) | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:72) |
| SR5 | Counter-tx for payment | `person → world`, same amount, same type, `reversal_of=original` | same as SR4 | [`test_reverse_counter_transactions_flip_funds`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:86) |
| SR6 | Counter-txs preserve type + amount | `counter.type == original.type`, `counter.amount == original.amount` | same as SR4 | [`test_reverse_counter_transactions_preserve_type`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:96) |
| SR7 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:226) | [`test_reversal_operation_owns_no_transactions`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:161) |
| SR8 | Person fund restored | `person.balance` back to pre-create baseline | `balance_at` | [`test_receiver_balance_restored_to_zero_after_reversal`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:124) |
| SR9 | Settlement state cleared | `amount_settled == 0`, `is_fully_settled == False` | `amount_settled` | [`test_reversal_clears_settlement_state`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:165) |
| SR10 | Reason flows to reversal | `reversal.description` contains the reason | [`ReversableModel.reverse()`](../../apps/app_base/models.py:262) | [`test_reason_flows_to_reversal_description`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:172) |
| SR11 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger) | whole engine | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:138) |

### 5.3 `pay` (one-shot guard)

There is **no standalone pay action** for Cash Injection:

| Branch | Behavior | Enforced by | Pinned by test |
|--------|----------|-------------|----------------|
| `process_payment()` called | no-op (returns immediately — `can_pay=False`) | [`process_payment`](../../apps/app_operation/models/operation.py:686) | n/a (covered by `can_pay=False`) |
| `create_payment_transaction()` called after create | `ValidationError` — one-shot allows a single payment only, amount must equal `op.amount` | [`create_payment_transaction`](../../apps/app_base/mixins.py:391) | [`test_one_shot_prevents_second_payment`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:204) |

### 5.4 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by [`ImmutableMixin`](../../apps/app_base/mixins.py:30) via `_immutable_fields` ([`operation.py`](../../apps/app_operation/models/operation.py:51)).

| Branch | Enforced by | Pinned by test |
|--------|-------------|----------------|
| `source` changed after save | `ImmutableMixin.save()` | [`test_source_is_immutable`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:174) |
| `destination` changed after save | `ImmutableMixin.save()` | [`test_destination_is_immutable`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:183) |
| `amount` changed after save | `ImmutableMixin.save()` | [`test_amount_is_immutable`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:192) |

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — [`Entity.save()`](../../apps/app_entity/models/__init__.py:714).
- The operation's governing entity (`period_entity`) is the **destination person** (`_dest_role = "url"`) — [`Operation.period_entity`](../../apps/app_operation/models/operation.py:491).
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC11).
- New operations dated inside a **closed** period are rejected (VC10) — [`is_date_in_closed_period`](../../apps/app_operation/models/period.py:14).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period ([`_reverse_period`](../../apps/app_operation/models/operation.py:455)).

---

## 7. Entity roles & balance contract

- Person is the only allowed destination; world the only allowed source — enforced at model (VC1/VC2) and transaction (VC13) layers.
- `person.balance` is derived exclusively from **payment-type** transactions (`balance_at`); the issuance tx never moves a balance.
- World is **virtual**: `can_pay` always returns `True`, so injections are never blocked by fund balance and can run arbitrarily many times (VC12).

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Create route | `POST/GET /<person_pk>/cash-injection/create` → [`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:75) |
| Source selection | locked to the single **World** entity (`_source_role="world"`, resolved by [`resolve_request`](../../apps/app_operation/models/operation.py:202)); no picker |
| Destination selection | the **Person** from the URL (`_dest_role="url"`); [`get_related_entities`](../../apps/app_operation/models/operation.py:440) returns `[]` → no secondary-entity field |
| Category | hidden (no category) |
| Amount | raw `amount` POST field ([`_compute_amount`](../../apps/app_operation/views/create_operation/base.py:52)); validated > 0 at model |
| POST parsing | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) — date format, description, category (n/a), `amount_paid` (n/a, forced 0) |
| List entry | "Cash Injection" link in [`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html:18) |
| Detail | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) — shows both transactions + settlement + reversal button |
| Reverse | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source=world · VC2 dest=person · VC3 source active · VC4 dest active · VC5 source fund active · VC6 target fund active · VC7 amount>0 · VC8 officer staff · VC9 officer active · VC10 not closed-period · VC11 covering period exists · VC12 balance exempt · VC13 tx entity-type · VC14 tx op-type · VC15 source≠target

**create — effects:** SC1 issuance tx · SC2 payment tx · SC3 amounts equal · SC4 direction world→person · SC5 settled immediately · SC6 person ▲ · SC7 world (virtual) ▼ · SC8 no invoice/movements · SC9 period assigned

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no explicit txs · VR4 no adjustments (n/a) · VR5 reason required (view)

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 identity copied · SR4 issuance counter-tx · SR5 payment counter-tx · SR6 type/amount preserved · SR7 reversal owns no txs · SR8 person restored · SR9 settlement cleared · SR10 reason in description · SR11 differential invariant

**pay / immutability:** BP1 `process_payment` no-op · BP2 `create_payment_transaction` blocked after create · IM1/IM2/IM3 source/destination/amount immutable

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| Tx creation + counts | [`test_creates_issuance_and_payment_transactions`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:47) | SC1, SC2 |
| Tx amounts | [`test_transaction_amounts_match_operation`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:64) | SC3 |
| Tx direction | [`test_transaction_funds_are_correct`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:71) | SC4 |
| Settlement | [`test_is_fully_settled_after_creation`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:86) | SC5 |
| Source/dest validation | [`test_source_must_be_world`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:98), [`test_destination_must_be_person_entity`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:105) | VC1, VC2 |
| Active entities | [`test_source_entity_must_be_active`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:112), [`test_destination_entity_must_be_active`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:120), [`test_source_entity_must_be_able_to_pay`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:128) | VC3–VC6 |
| Amount | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:140), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:145) | VC7 |
| Officer | [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:154), [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:162) | VC8, VC9 |
| Immutability | [`test_source_is_immutable`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:174), [`test_destination_is_immutable`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:183), [`test_amount_is_immutable`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:192) | IM1–IM3 |
| One-shot guard | [`test_one_shot_prevents_second_payment`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:204) | BP2 |
| Balance exempt | [`test_check_balance_on_payment_is_disabled`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:219), [`test_injection_succeeds_regardless_of_prior_injections`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:223) | VC12 |
| Person balance ▲ | [`test_receiver_balance_increases_after_cash_injection`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:233) | SC6 |
| Closed period | [`test_operation_blocked_when_destination_in_closed_period`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:248) | VC10 |
| No covering period | [`test_operation_blocked_when_no_covering_period`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:264) | VC11 |
| No invoice/movements | [`test_no_invoice_items_and_no_movements`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_create.py:278) | SC8 |
| Reverse happy path | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:46), [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:52), [`test_reversal_is_reversal`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:59), [`test_reverse_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:65) | SR1–SR3 |
| Counter txs | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:72), [`test_reverse_counter_transactions_flip_funds`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:86), [`test_reverse_counter_transactions_preserve_type`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:96) | SR4–SR6 |
| Reverse constraints | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:107), [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:114) | VR1, VR2 |
| Person balance restored | [`test_receiver_balance_restored_to_zero_after_reversal`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:124) | SR8 |
| Reversal owns no txs | [`test_reversal_operation_owns_no_transactions`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:161) | SR7 |
| Differential invariant | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:138) | SR11, SC7 |
| Settlement cleared | [`test_reversal_clears_settlement_state`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:165) | SR9 |
| Reason in description | [`test_reason_flows_to_reversal_description`](../../apps/app_operation/tests/operations/cash/test_cash_injection_cash_injection_reversal.py:172) | SR10 |

---

## 11. Tasks

- [x] Verify both `CASH_INJECTION_ISSUANCE` and `CASH_INJECTION_PAYMENT` are created on save
- [x] Verify transaction fund direction: `world.fund → person.fund` for both
- [x] Verify operation is fully settled immediately
- [x] Verify all validation branches VC1–VC15
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `create_payment_transaction()` is blocked after creation (one-shot)
- [x] Verify reversal creates counter-transactions: `person.fund → world.fund`
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify counter-transactions preserve transaction type
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [x] Verify person balance affected correctly by create (▲ amount)
- [x] Verify person balance affected correctly by reverse (restored)
- [x] UI: create form — source locked to World, destination = person from URL
- [x] UI: operation detail shows both transactions and reversal button
- [x] Complete test suite covering all branches; each test has a small number of assertions (one behavior per test)
- [ ] Register remaining operation specs under the same contract structure (see [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md))
