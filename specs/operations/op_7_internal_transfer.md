# Internal Transfer — Operation Contract

**Epic:** 10.1 — Miscellaneous One-Shot Operations
**Type:** One-shot, auto-settled
**Actions:** `create`, `reverse`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Internal Transfer** operation.
> Every clause below is registered to its implementing code (model → mixin → transaction → view) and to its pinning test.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> Other operations follow the same structure — see [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md).

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.INTERNAL_TRANSFER` (`"INTERNAL_TRANSFER"`) | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:11) |
| Proxy class | `InternalTransferOperation` | [`op_internal_transfer.py`](../../apps/app_operation/models/proxies/op_internal_transfer.py:8) |
| URL slug | `"internal-transfer"` | [`op_internal_transfer.py`](../../apps/app_operation/models/proxies/op_internal_transfer.py:12) |
| Label | `"Internal Transfer"` | [`op_internal_transfer.py`](../../apps/app_operation/models/proxies/op_internal_transfer.py:13) |
| Theme | `danger` / `bi-box-arrow-up-right` (inherited default — not overridden) | [`operation.py`](../../apps/app_operation/models/operation.py:112) |
| Source role | `url` (must be an internal Person) | [`op_internal_transfer.py`](../../apps/app_operation/models/proxies/op_internal_transfer.py:14) |
| Destination role | `post` (must be an internal Person, picked from secondary field) | [`op_internal_transfer.py`](../../apps/app_operation/models/proxies/op_internal_transfer.py:15) |
| Registered in | `PROXY_MAP` | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:33) |
| Cross-op reference | row IT | [`operations-comparison.md`](operations-comparison.md) |

**Configuration flags** (all on [`op_internal_transfer.py`](../../apps/app_operation/models/proxies/op_internal_transfer.py:8)):

| Flag | Value | Meaning |
|------|-------|---------|
| `_issuance_transaction_type` | `INTERNAL_TRANSFER_ISSUANCE` | issuance tx created on save |
| `_payment_transaction_type` | `INTERNAL_TRANSFER_PAYMENT` | payment tx created on save (one-shot) |
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
| Proxy class + type-specific config + `clean()` (internal/source/dest/system-world guards + balance) | [`op_internal_transfer.py`](../../apps/app_operation/models/proxies/op_internal_transfer.py:8) |
| Destination picker (`get_related_entities` — all Persons except the URL person) | [`op_internal_transfer.py`](../../apps/app_operation/models/proxies/op_internal_transfer.py:36) |
| Proxy registry / URL→class resolution | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:33) |
| Shared `Operation` engine (`clean`, `save`, `reverse`, `create`, `resolve_request`, period assignment, reversable tx types) | [`operation.py`](../../apps/app_operation/models/operation.py:34) |
| Operation type enum | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:11) |

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
| Payer balance check at create (via `fund.can_pay`) | [`op_internal_transfer.py:clean()`](../../apps/app_operation/models/proxies/op_internal_transfer.py:63) |
| One-shot guard (single payment, amount == op.amount) | [`LinkedPaymentTransactionMixin.create_payment_transaction()`](../../apps/app_base/mixins.py:391) |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | [`ReversableModel`](../../apps/app_base/models.py:133) + [`Operation.reverse()`](../../apps/app_operation/models/operation.py:997) |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | [`models.py`](../../apps/app_transaction/models.py:33) |
| `INTERNAL_TRANSFER_ISSUANCE` (non-virtual → non-virtual) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:366), entity map [:555](../../apps/app_transaction/transaction_type.py:555), op map [:636](../../apps/app_transaction/transaction_type.py:636) |
| `INTERNAL_TRANSFER_PAYMENT` (non-virtual → non-virtual, affects balance) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:376), entity map [:556](../../apps/app_transaction/transaction_type.py:556), op map [:637](../../apps/app_transaction/transaction_type.py:637), payment set [:437](../../apps/app_transaction/transaction_type.py:437) |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Person balance = incoming payment txs − outgoing payment txs | [`Entity.balance`](../../apps/app_entity/models/__init__.py:668) → [`balance_at`](../../apps/app_entity/models/__init__.py:414) |
| `is_internal` flag (both sides must be internal — VC1/VC2) | [`Entity.is_internal`](../../apps/app_entity/models/__init__.py:245) |
| `is_virtual` flag (system/world excluded — VC3/VC4) | [`Entity.is_virtual`](../../apps/app_entity/models/__init__.py:265) |
| Balance enforcement: `can_pay` only balance-checks real (non-virtual) internal funds | [`Entity.can_pay`](../../apps/app_entity/models/__init__.py:704) |
| Open financial period auto-created on entity creation | [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (generic, resolves URL person source + `post` person destination) | [`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:75) |
| POST parsing/validation | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) |
| Reverse view (reason required) | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) |
| Detail view (transactions + reversal button) | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) |
| URL: `/<pk>/<op_type>/create` | [`urls.py`](../../apps/app_operation/urls.py:142) |
| URL: `/<pk>/reverse/` | [`urls.py`](../../apps/app_operation/urls.py:192) |
| URL: `/<pk>/detail/` | [`urls.py`](../../apps/app_operation/urls.py:182) |
| Templates | [`generic_form.html`](../../apps/app_operation/templates/app_operation/generic_form.html), [`reverse_form.html`](../../apps/app_operation/templates/app_operation/reverse_form.html), [`operation_detail.html`](../../apps/app_operation/templates/app_operation/operation_detail.html), entry link in [`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html:98) |

### 2.6 Tests

| Concern | Test file |
|---------|-----------|
| Create branches | [`test_internal_transfer_internal_transfer_create.py`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py) |
| Reverse branches | [`test_internal_transfer_internal_transfer_reversal.py`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py) |
| Coverage manifest (executable branch registry) | [`tests/base.py`](../../apps/app_operation/tests/base.py:831) |

---

## 3. Money flow & entities

- **Source (payer):** the **internal Person** entity in the URL (`is_internal=True`). Its fund is the source fund and is **balance-checked at create** (VC12).
- **Destination (receiver):** an **internal Person** entity picked via the secondary field (`is_internal=True`). System and World are excluded on both sides (VC3/VC4).
- **Transaction flow** (both on create, source → destination):

> **Requirement — no virtual funds.** Neither the source nor the destination of an Internal Transfer may be a **virtual** entity (**System** or **World**) — virtual funds have no transferable internal balance, so transfers are strictly between **real internal funds**. Enforced at the model (VC3/VC4) and again at the transaction layer (VC15 — entity map requires `not_virtual` on both sides).

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `INTERNAL_TRANSFER_ISSUANCE` | `source.fund → destination.fund` | none (issuance, not a payment type) |
| 2 | `INTERNAL_TRANSFER_PAYMENT` | `source.fund → destination.fund` | ▼ source by `amount`; ▲ destination by `amount` |

- **Payment source fund:** `self.source` (internal person) — [`op_internal_transfer.py`](../../apps/app_operation/models/proxies/op_internal_transfer.py:29)
- **Payment target fund:** `self.destination` (internal person) — [`op_internal_transfer.py`](../../apps/app_operation/models/proxies/op_internal_transfer.py:33)

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

Entry points: model `InternalTransferOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx, then payment tx).

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source is internal | `source.is_internal` | `ValidationError` | `"Internal Transfer source must be an internal entity."` | [`clean()`](../../apps/app_operation/models/proxies/op_internal_transfer.py:47) | [`test_non_internal_source_raises_validation_error`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:126) |
| VC2 | Destination is internal | `destination.is_internal` | `ValidationError` | `"Internal Transfer destination must be an internal entity."` | [`clean()`](../../apps/app_operation/models/proxies/op_internal_transfer.py:51) | [`test_non_internal_destination_raises_validation_error`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:168) |
| VC3 | Source not system/world | `not (source.is_system or source.is_world)` | `ValidationError` | `"Internal Transfer source cannot be a system or world entity."` | [`clean()`](../../apps/app_operation/models/proxies/op_internal_transfer.py:55) | [`test_system_entity_as_source_raises_validation_error`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:132), [`test_world_entity_as_source_raises_validation_error`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:138) |
| VC4 | Destination not system/world | `not (destination.is_system or destination.is_world)` | `ValidationError` | `"Internal Transfer destination cannot be a system or world entity."` | [`clean()`](../../apps/app_operation/models/proxies/op_internal_transfer.py:59) | [`test_system_entity_as_destination_raises_validation_error`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:176), [`test_world_entity_as_destination_raises_validation_error`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:182) |
| VC5 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | [`test_source_must_be_active`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:143) |
| VC6 | Destination entity active | `destination.active` | `ValidationError` | same as VC5 | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | [`test_destination_must_be_active`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:187) |
| VC7 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | [`SourceFundMixin`](../../apps/app_base/mixins.py:132) | merged with VC5 ([`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:151)) |
| VC8 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | [`TargetFundMixin`](../../apps/app_base/mixins.py:152) | merged with VC6 |
| VC9 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | [`AmountCleanMixin`](../../apps/app_base/mixins.py:69) | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:199), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:204) |
| VC10 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:81) | [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:213) |
| VC11 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:84) | [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:221) |
| VC12 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:541) | covered by the shared period suite (see §10) |
| VC13 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) | covered by the shared period suite (see §10) |
| VC14 | Balance checked at create (source pays) | `payment_source_fund.can_pay(amount)` | `ValidationError` | `"Insufficient funds: source fund balance (%(balance)s) is less than transfer amount (%(amount)s)."` | [`op_internal_transfer.py:clean()`](../../apps/app_operation/models/proxies/op_internal_transfer.py:66) → [`Entity.can_pay`](../../apps/app_entity/models/__init__.py:704) | [`test_source_insufficient_balance_raises_validation_error`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:159), [`test_check_balance_on_payment_is_disabled`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:279) |
| VC15 | Tx entity-type contract | `source.is_virtual == False` and `target.is_virtual == False` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | [`Transaction.create()`](../../apps/app_transaction/models.py:144) + map [:555](../../apps/app_transaction/transaction_type.py:555) | implied by VC1–VC4 (model clean blocks first) |
| VC16 | Tx operation-type allowed | document is `INTERNAL_TRANSFER` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | [`Transaction.create()`](../../apps/app_transaction/models.py:155) + map [:636](../../apps/app_transaction/transaction_type.py:636) | implied by VC1–VC4 |
| VC17 | Source ≠ destination | distinct internal persons | `ValidationError` | `"Source and target funds must be different."` | [`Transaction.clean()`](../../apps/app_transaction/models.py:107) + picker excludes URL person | structural (picker excludes the URL person) |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | 1 × `INTERNAL_TRANSFER_ISSUANCE`, amount `== op.amount`, `source → destination` | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:222) | [`test_creates_issuance_and_payment_transactions`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:70) |
| SC2 | Payment tx created | 1 × `INTERNAL_TRANSFER_PAYMENT`, amount `== op.amount`, `source → destination` | [`LinkedPaymentTransactionMixin.save()`](../../apps/app_base/mixins.py:424) | same as SC1 |
| SC3 | Tx amounts equal op amount | both txs `amount == op.amount` | transaction creation | shared engine (see §11 — no dedicated focused test yet) |
| SC4 | Tx fund direction | both txs `source=source`, `target=destination` | [`op_internal_transfer.py`](../../apps/app_operation/models/proxies/op_internal_transfer.py:29) | [`test_transaction_funds_are_correct`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:84) |
| SC5 | Fully settled immediately | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:268) | [`test_is_fully_settled_immediately`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:92) |
| SC6 | Source fund ▼ amount | `source.balance` decreases by `amount` | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) | [`test_source_balance_decreases_after_transfer`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:100) |
| SC7 | Destination fund ▲ amount | `destination.balance` increases by `amount` | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) | [`test_destination_balance_increases_after_transfer`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:111) |
| SC8 | No invoice / no movements | `has_invoice=False`; no invoice items; no movement lines | `has_invoice=False` | config flag (`has_invoice=False`); no ledger/movement machinery in `post_save_tasks` |
| SC9 | Period auto-assigned | `period` = the source's covering period (open period auto-created at entity creation) | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) + [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) | covered by shared period suite |

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:34) | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:146) |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:47) | [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:153) |
| VR3 | No explicit txs to reverse | all txs are implicit (one-shot issuance + payment) | `ValidationError` (would require manual reversal) | `"You can't reverse this object as it has non-reversed transactions…"` | [`ReversableModel._requires_transaction_reversal`](../../apps/app_base/models.py:203) + [`Operation._implicit_reversable_transaction_types`](../../apps/app_operation/models/operation.py:478) | implied by successful reverse ([`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:96)) |
| VR4 | No non-reversed adjustments | n/a — Internal Transfer is not adjustable | never fails | — | `is_adjustable=False` | n/a |
| VR5 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:82) | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:235) | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:70) |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:270) | [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:76) |
| SR3 | Reversal inherits identity | `amount`, `source`, `destination` copied | [`ReversableModel._get_reverse_kwargs`](../../apps/app_base/models.py:184) | [`test_reverse_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:89) |
| SR4 | Counter-tx for issuance | `destination → source`, same amount, same type, `reversal_of=original` | [`Transaction.reverse()`](../../apps/app_transaction/models.py:206) | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:96) |
| SR5 | Counter-tx for payment | `destination → source`, same amount, same type, `reversal_of=original` | same as SR4 | [`test_reverse_counter_transactions_flip_funds`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:105) |
| SR6 | Counter-txs preserve type + amount | `counter.type == original.type`, `counter.amount == original.amount` | same as SR4 | [`test_reverse_counter_transactions_preserve_type`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:115) |
| SR7 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:226) | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:100) |
| SR8 | Source + destination restored | both balances back to pre-create baseline | `balance_at` | [`test_source_balance_restored_after_reversal`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:122), [`test_destination_balance_restored_after_reversal`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:132) |
| SR9 | Settlement state cleared | `amount_settled == 0`, `is_fully_settled == False` | `amount_settled` | differential invariant ([`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:163)); no dedicated focused test yet (see §11) |
| SR10 | Reason flows to reversal | `reversal.description` contains the reason | [`ReversableModel.reverse()`](../../apps/app_base/models.py:262) | shared engine (see §11 — no dedicated focused test yet) |
| SR11 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger) | whole engine | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:163) |

### 5.3 `pay` (one-shot guard)

There is **no standalone pay action** for Internal Transfer:

| Branch | Behavior | Enforced by | Pinned by test |
|--------|----------|-------------|----------------|
| `process_payment()` called | no-op (returns immediately — `can_pay=False`) | [`process_payment`](../../apps/app_operation/models/operation.py:686) | n/a (covered by `can_pay=False`) |
| `create_payment_transaction()` called after create | `ValidationError` — one-shot allows a single payment only, amount must equal `op.amount` (balance re-checked first, VC14) | [`create_payment_transaction`](../../apps/app_base/mixins.py:391) | [`test_one_shot_prevents_second_payment`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:264) |

### 5.4 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by [`ImmutableMixin`](../../apps/app_base/mixins.py:30) via `_immutable_fields` ([`operation.py`](../../apps/app_operation/models/operation.py:51)).

| Branch | Enforced by | Pinned by test |
|--------|-------------|----------------|
| `source` changed after save | `ImmutableMixin.save()` | [`test_source_is_immutable`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:233) |
| `destination` changed after save | `ImmutableMixin.save()` | [`test_destination_is_immutable`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:243) |
| `amount` changed after save | `ImmutableMixin.save()` | [`test_amount_is_immutable`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:252) |

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — [`Entity.save()`](../../apps/app_entity/models/__init__.py:714).
- The operation's governing entity (`period_entity`) is the **source person** (`_source_role = "url"`) — [`Operation.period_entity`](../../apps/app_operation/models/operation.py:498).
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC13).
- New operations dated inside a **closed** period are rejected (VC12) — [`is_date_in_closed_period`](../../apps/app_operation/models/period.py:14).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period ([`_reverse_period`](../../apps/app_operation/models/operation.py:455)).

---

## 7. Entity roles & balance contract

- **Requirement — no virtual funds.** A virtual entity (**System** or **World**) can never be the source or the destination of an Internal Transfer, because a virtual fund cannot own a transferable balance. Enforced at model `clean()` (VC3/VC4 — `"Internal Transfer source/destination cannot be a system or world entity."`) and again at the transaction layer (VC15 — entity map requires `not_virtual` on both sides, [`transaction_type.py:555`](../../apps/app_transaction/transaction_type.py:555)).
- Both sides must additionally be **internal** (VC1/VC2) — enforced at model `clean()`.
- `source.balance` / `destination.balance` are derived exclusively from **payment-type** transactions (`balance_at`); the issuance tx never moves a balance.
- The source fund is a **real internal fund** and is balance-checked at create (`clean()`, VC14). `check_balance_on_payment` stays `False` — the balance is guaranteed once at creation, and the one-shot payment then matches it exactly.
- Source ≠ destination is guaranteed structurally by the picker (which excludes the URL person) plus the `Transaction.clean()` guard (VC17).

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Create route | `POST/GET /<person_pk>/internal-transfer/create` → [`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:75) |
| Source selection | the **internal Person** from the URL (`_source_role="url"`, resolved by [`resolve_request`](../../apps/app_operation/models/operation.py:202)); no picker |
| Destination selection | an **internal Person** picked from the secondary field (`_dest_role="post"`); [`get_related_entities`](../../apps/app_operation/models/proxies/op_internal_transfer.py:36) returns all Person entities except the URL person (internal-ness enforced at model `clean()`) |
| Category | hidden (no category) |
| Amount | raw `amount` POST field ([`_compute_amount`](../../apps/app_operation/views/create_operation/base.py:52)); validated > 0 at model; balance-checked at create (VC14) |
| POST parsing | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) — date format, description, category (n/a), `amount_paid` (n/a, forced 0) |
| List entry | "Internal Transfer" link in [`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html:98) |
| Detail | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) — shows both transactions + settlement + reversal button |
| Reverse | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source internal · VC2 dest internal · VC3 source not system/world · VC4 dest not system/world · VC5 source active · VC6 dest active · VC7 source fund active · VC8 target fund active · VC9 amount>0 · VC10 officer staff · VC11 officer active · VC12 not closed-period · VC13 covering period exists · VC14 balance checked (clean) · VC15 tx entity-type · VC16 tx op-type · VC17 source≠destination

**create — effects:** SC1 issuance tx · SC2 payment tx · SC3 amounts equal · SC4 direction source→destination · SC5 settled immediately · SC6 source ▼ · SC7 destination ▲ · SC8 no invoice/movements · SC9 period assigned

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no explicit txs · VR4 no adjustments (n/a) · VR5 reason required (view)

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 identity copied · SR4 issuance counter-tx · SR5 payment counter-tx · SR6 type/amount preserved · SR7 reversal owns no txs · SR8 source+destination restored · SR9 settlement cleared · SR10 reason in description · SR11 differential invariant

**pay / immutability:** BP1 `process_payment` no-op · BP2 `create_payment_transaction` blocked after create · IM1/IM2/IM3 source/destination/amount immutable

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| Tx creation + counts | [`test_creates_issuance_and_payment_transactions`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:70) | SC1, SC2 |
| Tx direction | [`test_transaction_funds_are_correct`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:84) | SC4 |
| Settlement | [`test_is_fully_settled_immediately`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:92) | SC5 |
| Source internal | [`test_non_internal_source_raises_validation_error`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:126), [`test_system_entity_as_source_raises_validation_error`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:132), [`test_world_entity_as_source_raises_validation_error`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:138) | VC1, VC3 |
| Destination internal | [`test_non_internal_destination_raises_validation_error`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:168), [`test_system_entity_as_destination_raises_validation_error`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:176), [`test_world_entity_as_destination_raises_validation_error`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:182) | VC2, VC4 |
| Active entities | [`test_source_must_be_active`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:143), [`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:151), [`test_destination_must_be_active`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:187) | VC5–VC8 |
| Balance check | [`test_source_insufficient_balance_raises_validation_error`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:159), [`test_check_balance_on_payment_is_disabled`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:279) | VC14 |
| Amount | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:199), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:204) | VC9 |
| Officer | [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:213), [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:221) | VC10, VC11 |
| Immutability | [`test_source_is_immutable`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:233), [`test_destination_is_immutable`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:243), [`test_amount_is_immutable`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:252) | IM1–IM3 |
| One-shot guard | [`test_one_shot_prevents_second_payment`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:264) | BP2 |
| Source ▼ / destination ▲ | [`test_source_balance_decreases_after_transfer`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:100), [`test_destination_balance_increases_after_transfer`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_create.py:111) | SC6, SC7 |
| Reverse happy path | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:70), [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:76), [`test_reversal_is_reversal`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:83), [`test_reverse_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:89) | SR1–SR3 |
| Counter txs | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:96), [`test_reverse_counter_transactions_flip_funds`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:105), [`test_reverse_counter_transactions_preserve_type`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:115) | SR4–SR7 |
| Reverse constraints | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:146), [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:153) | VR1, VR2 |
| Balance restored | [`test_source_balance_restored_after_reversal`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:122), [`test_destination_balance_restored_after_reversal`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:132) | SR8 |
| Differential invariant | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/transfer/test_internal_transfer_internal_transfer_reversal.py:163) | SR11, SR9 |

---

## 11. Tasks

- [x] Verify both `INTERNAL_TRANSFER_ISSUANCE` and `INTERNAL_TRANSFER_PAYMENT` are created on save
- [x] Verify transaction fund direction: `source.fund → destination.fund` for both
- [x] Verify operation is fully settled immediately
- [x] Verify all validation branches VC1–VC17 (internal, non-virtual, balance, active, amount, officer)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `create_payment_transaction()` is blocked after creation (one-shot)
- [x] Verify reversal creates counter-transactions: `destination.fund → source.fund`
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify counter-transactions preserve transaction type
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [x] Verify source balance affected correctly by create (▼ amount) and destination (▲ amount)
- [x] Verify source + destination balances restored by reverse
- [x] UI: create form — source = person from URL, destination = person picker (internal-ness enforced at model)
- [x] UI: operation detail shows both transactions and reversal button
- [ ] Add a dedicated focused `test_transaction_amounts_match_operation` for Internal Transfer (SC3 currently pinned only by the shared engine)
- [ ] Add a dedicated focused `test_reversal_clears_settlement_state` for Internal Transfer (SR9 currently pinned only by the differential invariant)
- [ ] Add a dedicated focused `test_reason_flows_to_reversal_description` for Internal Transfer (SR10 currently pinned only by the shared engine)
