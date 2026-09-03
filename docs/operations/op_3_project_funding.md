# Project Funding — Operation Contract

**Epic:** 9.1 — Project Capital Operations
**Type:** One-shot, auto-settled
**Actions:** `create`, `reverse`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Project Funding** operation.
> Every clause below names its implementing code (model → mixin → transaction → view) and its pinning test — as plain names, never links, so renames do not break the spec.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> Other operations follow the same structure — see [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md).

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.PROJECT_FUNDING` (`"PROJECT_FUNDING"`) | |
| Proxy class | `ProjectFundingOperation` | |
| URL slug | `"project-funding"` | |
| Label | `"Project Funding"` | |
| Theme | `danger` / `bi-box-arrow-up-right` (inherited default — not overridden) | |
| Source role | `url` (must be a Person) | |
| Destination role | `post` (must be a Project, picked from secondary field) | |
| Registered in | `PROXY_MAP` | |

**Configuration flags**:

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

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row names the code that must honor it (plain names, no links).

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_source`/`clean_destination` + `clean()` (shareholder + balance) | |
| Project picker (`get_related_entities` — projects the URL person is a shareholder of) | |
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
| Payer balance check at create (via `fund.can_pay`) | |
| One-shot guard (single payment, amount == op.amount) | `LinkedPaymentTransactionMixin.create_payment_transaction()` |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | `ReversableModel` + `Operation.reverse()` |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | |
| `PROJECT_FUNDING_ISSUANCE` (shareholder → project) | |
| `PROJECT_FUNDING_PAYMENT` (shareholder → project, affects balance) | |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Person balance = incoming payment txs − outgoing payment txs | `Entity.balance` → `balance_at` |
| Balance enforcement: `can_pay` only balance-checks real (non-virtual) internal funds | `Entity.can_pay` |
| Role flags `is_person` / `is_project` | `is_person`, `is_project` |
| Active-shareholder relationship (used by `clean()` + picker) | `Stakeholder` + `StakeholderRole.SHAREHOLDER` |
| Open financial period auto-created on entity creation | `Entity.save()` |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (generic, resolves URL person source + `post` project destination) | `OperationCreateView` |
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

- **Source (payer):** the **Person** (shareholder/funder) entity in the URL (`is_person=True`). Its fund is the source fund and is **balance-checked at create** (VC12) — the funder's real internal fund must cover `amount`.
- **Destination (receiver):** the **Project** entity selected via the secondary field (`is_project=True`). The funder must be a registered **active shareholder** of that project (VC16).
- **Transaction flow** (both on create, person → project):

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `PROJECT_FUNDING_ISSUANCE` | `person.fund → project.fund` | none (issuance, not a payment type) |
| 2 | `PROJECT_FUNDING_PAYMENT` | `person.fund → project.fund` | ▼ funder person by `amount`; ▲ project by `amount` |

- **Payment source fund:** `self.source` (funder person)
- **Payment target fund:** `self.destination` (project)
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

Entry points: model `ProjectFundingOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx, then payment tx).

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source is Person | `source.is_person` | `ValidationError` | `"Project Funding source must be a Person entity."` | `clean_source` | `ProjectFundingCreateTest.test_source_must_be_person_entity` |
| VC2 | Destination is Project | `destination.is_project` | `ValidationError` | `"Project Funding destination must be a Project entity."` | `clean_destination` | `ProjectFundingCreateTest.test_destination_must_be_project_entity` |
| VC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | `Operation.clean()` | `ProjectFundingCreateTest.test_source_entity_must_be_active` |
| VC4 | Destination entity active | `destination.active` | `ValidationError` | same as VC3 | `Operation.clean()` | `ProjectFundingCreateTest.test_destination_entity_must_be_active` |
| VC5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | `SourceFundMixin` | `ProjectFundingCreateTest.test_source_fund_must_be_active` |
| VC6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | `TargetFundMixin` | merged with VC4 |
| VC7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | `ProjectFundingCreateTest.test_amount_zero_raises_validation_error` · `test_amount_negative_raises_validation_error` |
| VC8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | `OfficerMixin` | `ProjectFundingCreateTest.test_officer_user_must_be_staff` |
| VC9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | `OfficerMixin` | `ProjectFundingCreateTest.test_officer_must_be_active` |
| VC10 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | `Operation.clean()` | `ProjectFundingCreateTest.test_operation_blocked_when_source_in_closed_period` · `test_operation_blocked_when_destination_in_closed_period` |
| VC11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | `Operation.save()` | shared period suite (`OperationPeriodAssignmentTest.test_operation_raises_when_no_open_period`) |
| VC12 | Balance checked at create (funder pays) | `payment_source_fund.can_pay(amount)` | `ValidationError` | `"Insufficient funds: balance is %(balance)s, cannot fund %(amount)s."` | `Entity.can_pay` | `ProjectFundingCreateTest.test_amount_exceeding_funder_balance_raises_error` · `test_amount_equal_to_funder_balance_succeeds` |
| VC13 | Tx entity-type contract | `source.is_person` and `target.is_project` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | `Transaction.create()` | implied by VC1/VC2 (model clean blocks first) |
| VC14 | Tx operation-type allowed | document is `PROJECT_FUNDING` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | `Transaction.create()` | implied by VC1/VC2 |
| VC15 | Source ≠ target | person ≠ project | always true | `"Source and target funds must be different."` | `Transaction.clean()` | structural (person ≠ project) |
| VC16 | Source is active shareholder of destination | an active `StakeholderRole.SHAREHOLDER` link exists from the project to the source | `ValidationError` | `"The funding source must be a registered shareholder of the project."` | | `ProjectFundingCreateTest.test_source_must_be_shareholder_of_destination_project` |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | 1 × `PROJECT_FUNDING_ISSUANCE`, amount `== op.amount`, `person → project` | `LinkedIssuanceTransactionMixin.save()` | `ProjectFundingCreateTest.test_creates_issuance_and_payment_transactions` |
| SC2 | Payment tx created | 1 × `PROJECT_FUNDING_PAYMENT`, amount `== op.amount`, `person → project` | `LinkedPaymentTransactionMixin.save()` | same as SC1 |
| SC3 | Tx amounts equal op amount | both txs `amount == op.amount` | transaction creation | `ProjectFundingCreateTest.test_transaction_amounts_match_operation` |
| SC4 | Tx fund direction | both txs `source=person`, `target=project` | | `ProjectFundingCreateTest.test_transaction_funds_are_correct` |
| SC5 | Fully settled immediately | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | `LinkedPaymentTransactionMixin` | `ProjectFundingCreateTest.test_is_fully_settled_after_creation` |
| SC6 | Project fund ▲ amount | `project.balance` increases by `amount` | `Entity.balance_at` | `ProjectFundingCreateTest.test_project_fund_increases_after_funding` |
| SC7 | Funder fund ▼ amount | `person.balance` decreases by `amount` | `Entity.balance_at` | `ProjectFundingCreateTest.test_funder_fund_decreases_after_funding` |
| SC8 | No invoice / no movements | `has_invoice=False`; no invoice items; no movement lines | `has_invoice=False` | config flag (`has_invoice=False`); no ledger/movement machinery in `post_save_tasks` |
| SC9 | Period auto-assigned | `period` = the funder's covering period (open period auto-created at entity creation) | `Operation.save()` + `Entity.save()` | shared period suite (`OperationPeriodAssignmentTest`) |

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | `ReversableModel._validate_can_be_reversed` + view guard | `ProjectFundingReversalTest.test_cannot_reverse_already_reversed_operation` |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | `ReversableModel._validate_can_be_reversed` + view guard | `ProjectFundingReversalTest.test_cannot_reverse_a_reversal` |
| VR3 | No explicit txs to reverse | all txs are implicit (one-shot issuance + payment) | `ValidationError` (would require manual reversal) | `"You can't reverse this object as it has non-reversed transactions…"` | `ReversableModel._requires_transaction_reversal` + `Operation._implicit_reversable_transaction_types` | implied by successful reverse |
| VR4 | No non-reversed adjustments | n/a — Project Funding is not adjustable | never fails | — | `is_adjustable=False` | n/a |
| VR5 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | `operation_reverse_view` | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | `ReversableModel.reverse()` | `ProjectFundingReversalTest.test_reverse_creates_reversal_operation` |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | `ReversableModel.reverse()` | `ProjectFundingReversalTest.test_reverse_marks_original_as_reversed` |
| SR3 | Reversal inherits identity | `amount`, `source`, `destination` copied | `ReversableModel._get_reverse_kwargs` | `ProjectFundingReversalTest.test_reverse_inherits_amount_source_destination` |
| SR4 | Counter-tx for issuance | `project → person`, same amount, same type, `reversal_of=original` | `Transaction.reverse()` | `ProjectFundingReversalTest.test_reverse_creates_counter_transactions` |
| SR5 | Counter-tx for payment | `project → person`, same amount, same type, `reversal_of=original` | same as SR4 | `ProjectFundingReversalTest.test_reverse_creates_counter_transactions` |
| SR6 | Counter-txs preserve type + amount | `counter.type == original.type`, `counter.amount == original.amount` | same as SR4 | `ProjectFundingReversalTest.test_reverse_counter_transactions_flip_funds` · `test_reverse_counter_transactions_preserve_type` |
| SR7 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | `LinkedIssuanceTransactionMixin.save()` | implied by counter-tx tests (reversal created via `reverse()`) |
| SR8 | Funder + project restored | `person.balance` and `project.balance` back to pre-create baseline | `balance_at` | `ProjectFundingReversalTest.test_project_fund_restored_after_reversal` · `test_funder_fund_restored_after_reversal` |
| SR9 | Settlement state cleared | `amount_settled == 0`, `is_fully_settled == False` | `amount_settled` | `ProjectFundingReversalTest.test_reversal_clears_settlement_state` |
| SR10 | Reason flows to reversal | `reversal.description` contains the reason | `ReversableModel.reverse()` | `ProjectFundingReversalTest.test_reason_flows_to_reversal_description` |
| SR11 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger) | whole engine | `ProjectFundingReversalTest.test_create_then_reverse_leaves_world_unchanged` |

### 5.3 `pay` (one-shot guard)

There is **no standalone pay action** for Project Funding:

| Branch | Behavior | Enforced by | Pinned by test |
|--------|----------|-------------|----------------|
| `process_payment()` called | no-op (returns immediately — `can_pay=False`) | `process_payment` | n/a (covered by `can_pay=False`) |
| `create_payment_transaction()` called after create | `ValidationError` — one-shot allows a single payment only, amount must equal `op.amount` (balance re-checked first, VC12) | `create_payment_transaction` | `ProjectFundingCreateTest.test_one_shot_prevents_second_payment` |

### 5.4 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by `ImmutableMixin` via `_immutable_fields`.

| Branch | Enforced by | Pinned by test |
|--------|-------------|----------------|
| `source` changed after save | `ImmutableMixin.save()` | `ProjectFundingCreateTest.test_source_is_immutable` |
| `destination` changed after save | `ImmutableMixin.save()` | `ProjectFundingCreateTest.test_destination_is_immutable` |
| `amount` changed after save | `ImmutableMixin.save()` | `ProjectFundingCreateTest.test_amount_is_immutable` |

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — `Entity.save()`.
- The operation's governing entity (`period_entity`) is the **source funder person** (`_source_role = "url"`) — `Operation.period_entity`.
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC11).
- New operations dated inside a **closed** period are rejected (VC10) — checked for **both** source and destination entities; pinned by the closed-period regression tests (see §10).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period (`_reverse_period`).

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
| Create route | `POST/GET /<person_pk>/project-funding/create` → `OperationCreateView` |
| Source selection | the **Person (funder)** from the URL (`_source_role="url"`, resolved by `resolve_request`); no picker |
| Destination selection | a **Project** picked from the secondary field (`_dest_role="post"`); `get_related_entities` returns the projects for which the URL person is an active shareholder |
| Category | hidden (no category) |
| Amount | raw `amount` POST field (`_compute_amount`); validated > 0 at model; balance-checked at create (VC12) |
| POST parsing | `OperationDataValidator` — date format, description, category (n/a), `amount_paid` (n/a, forced 0) |
| List entry | "Project Funding" link |
| Detail | `operation_detail_view` — shows the operation total + settlement status + reversal action; the individual issuance/payment transactions are hidden (one-shot — two identical amounts would confuse users) |
| Reverse | `operation_reverse_view` — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

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
| Tx creation + counts | `ProjectFundingCreateTest.test_creates_issuance_and_payment_transactions` | SC1, SC2 |
| Tx amounts | `ProjectFundingCreateTest.test_transaction_amounts_match_operation` | SC3 |
| Tx direction | `ProjectFundingCreateTest.test_transaction_funds_are_correct` | SC4 |
| Settlement | `ProjectFundingCreateTest.test_is_fully_settled_after_creation` | SC5 |
| Source/dest validation | `ProjectFundingCreateTest.test_source_must_be_person_entity` · `test_destination_must_be_project_entity` | VC1, VC2 |
| Shareholder check | `ProjectFundingCreateTest.test_source_must_be_shareholder_of_destination_project` | VC16 |
| Active entities | `ProjectFundingCreateTest.test_source_entity_must_be_active` · `test_source_fund_must_be_active` · `test_destination_entity_must_be_active` | VC3–VC6 |
| Amount | `ProjectFundingCreateTest.test_amount_zero_raises_validation_error` · `test_amount_negative_raises_validation_error` | VC7 |
| Balance check | `ProjectFundingCreateTest.test_amount_exceeding_funder_balance_raises_error` · `test_amount_equal_to_funder_balance_succeeds` | VC12 |
| Officer | `ProjectFundingCreateTest.test_officer_user_must_be_staff` · `test_officer_must_be_active` | VC8, VC9 |
| Immutability | `ProjectFundingCreateTest.test_source_is_immutable` · `test_destination_is_immutable` · `test_amount_is_immutable` | IM1–IM3 |
| One-shot guard | `ProjectFundingCreateTest.test_one_shot_prevents_second_payment` | BP2 |
| Project ▲ / funder ▼ | `ProjectFundingCreateTest.test_project_fund_increases_after_funding` · `test_funder_fund_decreases_after_funding` | SC6, SC7 |
| Closed period | `ProjectFundingCreateTest.test_operation_blocked_when_source_in_closed_period` · `test_operation_blocked_when_destination_in_closed_period` | VC10 |
| Reverse happy path | `ProjectFundingReversalTest.test_reverse_creates_reversal_operation` · `test_reverse_marks_original_as_reversed` · `test_reverse_inherits_amount_source_destination` | SR1–SR3 |
| Counter txs | `ProjectFundingReversalTest.test_reverse_creates_counter_transactions` · `test_reverse_counter_transactions_flip_funds` · `test_reverse_counter_transactions_preserve_type` | SR4–SR7 |
| Reverse constraints | `ProjectFundingReversalTest.test_cannot_reverse_already_reversed_operation` · `test_cannot_reverse_a_reversal` | VR1, VR2 |
| Balance restored | `ProjectFundingReversalTest.test_project_fund_restored_after_reversal` · `test_funder_fund_restored_after_reversal` | SR8 |
| Settlement cleared | `ProjectFundingReversalTest.test_reversal_clears_settlement_state` | SR9 |
| Reason in description | `ProjectFundingReversalTest.test_reason_flows_to_reversal_description` | SR10 |
| Differential invariant | `ProjectFundingReversalTest.test_create_then_reverse_leaves_world_unchanged` | SR11, SR9 |

---
