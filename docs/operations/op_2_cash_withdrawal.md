# Cash Withdrawal — Operation Contract

**Epic:** 8.2 — Cash Operations
**Type:** One-shot, auto-settled
**Actions:** `create`, `reverse`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Cash Withdrawal** operation.
> Every clause below names its implementing code (model → mixin → transaction → view) and its pinning test — as plain names, never links, so renames do not break the spec.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> Other operations follow the same structure — see [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md).

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.CASH_WITHDRAWAL` (`"CASH_WITHDRAWAL"`) | |
| Proxy class | `CashWithdrawalOperation` | |
| URL slug | `"cash-withdrawal"` | |
| Label | `"Cash Withdrawal"` | |
| Theme | `danger` / `bi-box-arrow-up-right` (inherited default — not overridden) | |
| Source role | `url` (must be a Person) | |
| Destination role | `world` | |
| Registered in | `PROXY_MAP` | |

**Configuration flags:**

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

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row names the code that must honor it (plain names, no links).

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_source`/`clean_destination` | |
| Proxy registry / URL→class resolution | |
| Shared `Operation` engine (`clean`, `save`, `reverse`, `create`, `resolve_request`, period assignment, reversable tx types) | |
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
| One-shot payment tx creation + settlement (`amount_settled`, `is_fully_settled`) | `LinkedPaymentTransactionMixin` |
| Payer balance check before payment tx (`check_balance_on_payment=True` → `can_pay`) | `LinkedPaymentTransactionMixin.create_payment_transaction()` |
| One-shot guard (single payment, amount == op.amount) | `LinkedPaymentTransactionMixin.create_payment_transaction()` |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | `ReversableModel` + `Operation.reverse()` |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | |
| `CAPITAL_WITHDRAWAL_ISSUANCE` (person → world) | |
| `CAPITAL_WITHDRAWAL_PAYMENT` (person → world, affects balance) | |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Person balance = incoming payment txs − outgoing payment txs | `Entity.balance` → `balance_at` |
| Balance enforcement: `can_pay` only balance-checks real (non-virtual) internal funds | `Entity.can_pay` |
| Open financial period auto-created on entity creation | `Entity.save()` |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (generic, resolves URL person source + World destination) | `OperationCreateView` |
| POST parsing/validation | `OperationDataValidator` |
| Reverse view (reason required) | `operation_reverse_view` |
| Detail view (aggregate amount + reversal action; per-transaction list hidden — one-shot) | `operation_detail_view` |
| URL: `/<pk>/<op_type>/create` | |
| URL: `/<pk>/reverse/` | |
| URL: `/<pk>/detail/` | |
| Templates | |

### 2.6 Tests

| Concern | Test file |
|---------|-----------|
| Create branches | |
| Reverse branches | |
| Coverage manifest (executable branch registry) | |

---

## 3. Money flow & entities

- **Source (payer):** the **Person** entity in the URL (`is_person=True`). Its fund is the source fund and is **balance-checked** — the withdrawer's real internal fund must cover `amount` (VC12).
- **Destination (receiver):** the single **World** entity (`is_world=True`). Virtual — never balance-checked, exempt from period checks (world has no periods).
- **Transaction flow** (both on create, person → world):

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `CAPITAL_WITHDRAWAL_ISSUANCE` | `person.fund → world.fund` | none (issuance, not a payment type) |
| 2 | `CAPITAL_WITHDRAWAL_PAYMENT` | `person.fund → world.fund` | ▼ person fund by `amount` |

- **Payment source fund:** `self.source` (person)
- **Payment target fund:** `self.destination` (world)

---

## 4. Settlement model

Derived from `LinkedPaymentTransactionMixin` using payment-type transactions only:

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
| VC1 | Source is Person | `source.is_person` | `ValidationError` | `"Cash Withdrawal source must be a Person entity."` | `clean_source` | `CashWithdrawalCreateTest.test_source_must_be_person_entity` |
| VC2 | Destination is World | `destination.is_world` | `ValidationError` | `"Cash Withdrawal destination must be the World entity."` | `clean_destination` | `CashWithdrawalCreateTest.test_destination_must_be_world_entity` |
| VC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | `Operation.clean()` | `CashWithdrawalCreateTest.test_source_entity_must_be_active` |
| VC4 | Destination entity active | `destination.active` | `ValidationError` | same as VC3 | `Operation.clean()` | `CashWithdrawalCreateTest.test_destination_entity_must_be_active` |
| VC5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | `SourceFundMixin` | merged with VC3 |
| VC6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | `TargetFundMixin` | merged with VC4 (world is always active) |
| VC7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | `CashWithdrawalCreateTest.test_amount_zero_raises_validation_error` · `test_amount_negative_raises_validation_error` |
| VC8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | `OfficerMixin` | `CashWithdrawalCreateTest.test_officer_user_must_be_staff` |
| VC9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | `OfficerMixin` | `CashWithdrawalCreateTest.test_officer_must_be_active` |
| VC10 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | `Operation.clean()` | shared period suite (`OperationPeriodAssignmentTest.test_operation_in_closed_period_raises`) |
| VC11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | `Operation.save()` | shared period suite (`OperationPeriodAssignmentTest.test_operation_raises_when_no_open_period`) |
| VC12 | Balance checked (person payer) | `payment_source_fund.can_pay(amount)` | `ValidationError` | `"Insufficient funds: fund balance (%(balance)s) is less than the payment amount (%(amount)s)."` | `check_balance_on_payment=True` → `LinkedPaymentTransactionMixin.create_payment_transaction()` → `Entity.can_pay` | `CashWithdrawalCreateTest.test_insufficient_funds_blocked` · `test_withdrawal_without_sufficient_funds_raises_error` · `test_withdrawal_exceeding_balance_raises_error` |
| VC13 | Tx entity-type contract | `source.is_person` and `target.is_world` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | `Transaction.create()` | implied by VC1/VC2 (model clean blocks first) |
| VC14 | Tx operation-type allowed | document is `CASH_WITHDRAWAL` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | `Transaction.create()` | implied by VC1/VC2 |
| VC15 | Source ≠ target | person ≠ world | always true | `"Source and target funds must be different."` | `Transaction.clean()` | structural (person ≠ world) |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | 1 × `CAPITAL_WITHDRAWAL_ISSUANCE`, amount `== op.amount`, `person → world` | `LinkedIssuanceTransactionMixin.save()` | `CashWithdrawalCreateTest.test_creates_issuance_and_payment_transactions` |
| SC2 | Payment tx created | 1 × `CAPITAL_WITHDRAWAL_PAYMENT`, amount `== op.amount`, `person → world` | `LinkedPaymentTransactionMixin.save()` | same as SC1 |
| SC3 | Tx amounts equal op amount | both txs `amount == op.amount` | transaction creation | `CashWithdrawalCreateTest.test_transaction_amounts_match_operation` |
| SC4 | Tx fund direction | both txs `source=person`, `target=world` | | `CashWithdrawalCreateTest.test_transaction_funds_are_correct` |
| SC5 | Fully settled immediately | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | `LinkedPaymentTransactionMixin` | `CashWithdrawalCreateTest.test_is_fully_settled_after_creation` |
| SC6 | Person fund ▼ amount | `person.balance` decreases by `amount` | `Entity.balance_at` | `CashWithdrawalCreateTest.test_withdrawer_balance_decreases_after_withdrawal` |
| SC7 | World (virtual) ▲ | world balance moves but is never enforced / never read for checks | `can_pay` virtual exemption | differential invariant |
| SC8 | No invoice / no movements | `has_invoice=False`; no invoice items; no movement lines | `has_invoice=False` | config flag (`has_invoice=False`); no ledger/movement machinery in `post_save_tasks` |
| SC9 | Period auto-assigned | `period` = the withdrawer's covering period (open period auto-created at entity creation) | `Operation.save()` + `Entity.save()` | shared period suite (`OperationPeriodAssignmentTest`) |

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | `ReversableModel._validate_can_be_reversed` + view guard | `CashWithdrawalReversalTest.test_cannot_reverse_already_reversed_operation` |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | `ReversableModel._validate_can_be_reversed` + view guard | `CashWithdrawalReversalTest.test_cannot_reverse_a_reversal` |
| VR3 | No explicit txs to reverse | all txs are implicit (one-shot issuance + payment) | `ValidationError` (would require manual reversal) | `"You can't reverse this object as it has non-reversed transactions…"` | `ReversableModel._requires_transaction_reversal` + `Operation._implicit_reversable_transaction_types` | implied by successful reverse |
| VR4 | No non-reversed adjustments | n/a — Cash Withdrawal is not adjustable | never fails | — | `is_adjustable=False` | n/a |
| VR5 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | `operation_reverse_view` | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | `ReversableModel.reverse()` | `CashWithdrawalReversalTest.test_reverse_creates_reversal_operation` |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | `ReversableModel.reverse()` | `CashWithdrawalReversalTest.test_reverse_marks_original_as_reversed` |
| SR3 | Reversal inherits identity | `amount`, `source`, `destination` copied | `ReversableModel._get_reverse_kwargs` | `CashWithdrawalReversalTest.test_reverse_inherits_amount_source_destination` |
| SR4 | Counter-tx for issuance | `world → person`, same amount, same type, `reversal_of=original` | `Transaction.reverse()` | `CashWithdrawalReversalTest.test_reverse_creates_counter_transactions` |
| SR5 | Counter-tx for payment | `world → person`, same amount, same type, `reversal_of=original` | same as SR4 | `CashWithdrawalReversalTest.test_reverse_creates_counter_transactions` |
| SR6 | Counter-txs preserve type + amount | `counter.type == original.type`, `counter.amount == original.amount` | same as SR4 | `CashWithdrawalReversalTest.test_reverse_counter_transactions_flip_funds` · `test_reverse_counter_transactions_preserve_type` |
| SR7 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | `LinkedIssuanceTransactionMixin.save()` | implied by counter-tx tests (reversal created via `reverse()`) |
| SR8 | Person fund restored | `person.balance` back to pre-create baseline | `balance_at` | `CashWithdrawalReversalTest.test_withdrawer_balance_restored_after_reversal` |
| SR9 | Settlement state cleared | `amount_settled == 0`, `is_fully_settled == False` | `amount_settled` | `CashWithdrawalReversalTest.test_reversal_clears_settlement_state` |
| SR10 | Reason flows to reversal | `reversal.description` contains the reason | `ReversableModel.reverse()` | `CashWithdrawalReversalTest.test_reason_flows_to_reversal_description` |
| SR11 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger) | whole engine | `CashWithdrawalReversalTest.test_create_then_reverse_leaves_world_unchanged` |

### 5.3 `pay` (one-shot guard)

There is **no standalone pay action** for Cash Withdrawal:

| Branch | Behavior | Enforced by | Pinned by test |
|--------|----------|-------------|----------------|
| `process_payment()` called | no-op (returns immediately — `can_pay=False`) | `process_payment` | n/a (covered by `can_pay=False`) |
| `create_payment_transaction()` called after create | `ValidationError` — one-shot allows a single payment only, amount must equal `op.amount` (balance re-checked first, VC12) | `create_payment_transaction` | `CashWithdrawalCreateTest.test_one_shot_prevents_second_payment` |

### 5.4 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by `ImmutableMixin` via `_immutable_fields`.

| Branch | Enforced by | Pinned by test |
|--------|-------------|----------------|
| `source` changed after save | `ImmutableMixin.save()` | `CashWithdrawalCreateTest.test_source_is_immutable` |
| `destination` changed after save | `ImmutableMixin.save()` | `CashWithdrawalCreateTest.test_destination_is_immutable` |
| `amount` changed after save | `ImmutableMixin.save()` | `CashWithdrawalCreateTest.test_amount_is_immutable` |

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — `Entity.save()`.
- The operation's governing entity (`period_entity`) is the **source person** (`_source_role = "url"`) — `Operation.period_entity`.
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC11).
- New operations dated inside a **closed** period are rejected (VC10) — `is_date_in_closed_period`.
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period (`_reverse_period`).

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
| Create route | `POST/GET /<person_pk>/cash-withdrawal/create` → `OperationCreateView` |
| Source selection | the **Person** from the URL (`_source_role="url"`, resolved by `resolve_request`); no picker |
| Destination selection | locked to the single **World** entity (`_dest_role="world"`); `get_related_entities` returns `[]` → no secondary-entity field |
| Category | hidden (no category) |
| Amount | raw `amount` POST field (`_compute_amount`); validated > 0 at model; balance-checked at payment (VC12) |
| POST parsing | `OperationDataValidator` — date format, description, category (n/a), `amount_paid` (n/a, forced 0) |
| List entry | "Cash Withdrawal" list entry |
| Detail | `operation_detail_view` — shows the operation total + settlement status + reversal action; the individual issuance/payment transactions are hidden (one-shot — two identical amounts would confuse users) |
| Reverse | `operation_reverse_view` — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

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
| Tx creation + counts | `CashWithdrawalCreateTest.test_creates_issuance_and_payment_transactions` | SC1, SC2 |
| Tx amounts | `CashWithdrawalCreateTest.test_transaction_amounts_match_operation` | SC3 |
| Tx direction | `CashWithdrawalCreateTest.test_transaction_funds_are_correct` | SC4 |
| Settlement | `CashWithdrawalCreateTest.test_is_fully_settled_after_creation` | SC5 |
| Source/dest validation | `CashWithdrawalCreateTest.test_source_must_be_person_entity` · `test_destination_must_be_world_entity` | VC1, VC2 |
| Active entities | `CashWithdrawalCreateTest.test_source_entity_must_be_active` · `test_source_fund_must_be_active` · `test_destination_entity_must_be_active` | VC3–VC6 |
| Amount | `CashWithdrawalCreateTest.test_amount_zero_raises_validation_error` · `test_amount_negative_raises_validation_error` | VC7 |
| Officer | `CashWithdrawalCreateTest.test_officer_user_must_be_staff` · `test_officer_must_be_active` | VC8, VC9 |
| Immutability | `CashWithdrawalCreateTest.test_source_is_immutable` · `test_destination_is_immutable` · `test_amount_is_immutable` | IM1–IM3 |
| One-shot guard | `CashWithdrawalCreateTest.test_one_shot_prevents_second_payment` | BP2 |
| Person balance ▼ | `CashWithdrawalCreateTest.test_withdrawer_balance_decreases_after_withdrawal` | SC6 |
| Balance check enabled | `CashWithdrawalCreateTest.test_check_balance_on_payment_is_enabled` · `test_injection_then_withdrawal_succeeds` | VC12 |
| Insufficient funds | `CashWithdrawalCreateTest.test_insufficient_funds_blocked` · `test_withdrawal_without_sufficient_funds_raises_error` · `test_withdrawal_exceeding_balance_raises_error` | VC12 |
| Closed / covering period | shared period suite (`OperationPeriodAssignmentTest`) | VC10, VC11, SC9 |
| Reverse happy path | `CashWithdrawalReversalTest.test_reverse_creates_reversal_operation` · `test_reverse_marks_original_as_reversed` · `test_reverse_inherits_amount_source_destination` | SR1–SR3 |
| Counter txs | `CashWithdrawalReversalTest.test_reverse_creates_counter_transactions` · `test_reverse_counter_transactions_flip_funds` · `test_reverse_counter_transactions_preserve_type` | SR4–SR7 |
| Reverse constraints | `CashWithdrawalReversalTest.test_cannot_reverse_already_reversed_operation` · `test_cannot_reverse_a_reversal` | VR1, VR2 |
| Person balance restored | `CashWithdrawalReversalTest.test_withdrawer_balance_restored_after_reversal` | SR8 |
| Settlement cleared | `CashWithdrawalReversalTest.test_reversal_clears_settlement_state` | SR9 |
| Reason in description | `CashWithdrawalReversalTest.test_reason_flows_to_reversal_description` | SR10 |
| Differential invariant | `CashWithdrawalReversalTest.test_create_then_reverse_leaves_world_unchanged` | SR11, SC7, SR9 |

---
