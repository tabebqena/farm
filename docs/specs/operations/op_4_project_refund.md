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
| Operation type | `OperationType.PROJECT_REFUND` (`"PROJECT_REFUND"`) | |
| Proxy class | `ProjectRefundOperation` | |
| URL slug | `"project-refunding"` | |
| Label | `"Project Refund"` | |
| Theme | `success` / `bi-box-arrow-in-down` | |
| Source role | `post` (must be a Project, picked from secondary field) | |
| Destination role | `url` (must be a Person) | |
| Registered in | `PROXY_MAP` | |
| Cross-op reference | row PR | [`operations-comparison.md`](operations-comparison.md) |

**Configuration flags**:

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
| Proxy class + type-specific config + `clean_source`/`clean_destination` + `clean()` (shareholder, balance, net-funded cap) | |
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
| Payer balance check + net-funded cap at create | |
| One-shot guard (single payment, amount == op.amount) | `LinkedPaymentTransactionMixin.create_payment_transaction()` |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | `ReversableModel` + `Operation.reverse()` |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | |
| `PROJECT_REFUND_ISSUANCE` (project → shareholder) | |
| `PROJECT_REFUND_PAYMENT` (project → shareholder, affects balance) | |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Person balance = incoming payment txs − outgoing payment txs | `Entity.balance` → `balance_at` |
| Payables / receivables (one-shot nets to zero — SE4) | `Entity.payables`, `Entity.receivables` |
| Balance enforcement: `can_pay` only balance-checks real (non-virtual) internal funds | `Entity.can_pay` |
| Role flags `is_person` / `is_project` | `is_person`, `is_project` |
| Active-shareholder relationship (used by `clean()` + picker) | `Stakeholder` + `StakeholderRole.SHAREHOLDER` |
| Open financial period auto-created on entity creation | `Entity.save()` |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (generic, resolves `post` project source + URL person destination) | `OperationCreateView` |
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

- **Source (payer):** the **Project** entity selected via the secondary field (`is_project=True`). Its fund is the source fund and is **balance-checked at create** (VC12).
- **Destination (receiver):** the **Person** (shareholder) entity in the URL (`is_person=True`). It must be a registered **active shareholder** of the source project (VC16), and the refund is capped by the shareholder's **net funded amount** into that project (VC17).
- **Transaction flow** (both on create, project → person):

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `PROJECT_REFUND_ISSUANCE` | `project.fund → person.fund` | none (issuance, not a payment type) |
| 2 | `PROJECT_REFUND_PAYMENT` | `project.fund → person.fund` | ▼ project by `amount`; ▲ shareholder by `amount` |

- **Payment source fund:** `self.source` (project)
- **Payment target fund:** `self.destination` (shareholder person)
---

## 4. Settlement model

Derived from `LinkedPaymentTransactionMixin` using payment-type transactions only:

| Property | After create | After reverse |
|----------|--------------|---------------|
| `amount_settled` | `== amount` | `0.00` |
| `total_settlable_amount` (`effective_amount`) | `== amount` (no adjustments) | unchanged |
| `amount_remaining_to_settle` | `0.00` | `== amount` |
| `is_fully_settled` | `True` | `False` |

Because the operation is one-shot and never adjustable, settlement is **immediate and terminal** — there is no standalone `pay` action. The immediate tles the issuance, so **payables/receivables net to zero** at all times (SE4/SR12).

---

## 5. Actions

### 5.1 `create`

Entry points: model `ProjectRefundOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx, then payment tx).

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source is Project | `source.is_project` | `ValidationError` | `"Project Refund source must be a Project entity."` | `clean_source` | |
| VC2 | Destination is Person | `destination.is_person` | `ValidationError` | `"Project Refund destination must be a Person entity."` | `clean_destination` | |
| VC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | `Operation.clean()` | |
| VC4 | Destination entity active | `destination.active` | `ValidationError` | same as VC3 | `Operation.clean()` | |
| VC5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | `SourceFundMixin` | merged with VC3 |
| VC6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | `TargetFundMixin` | merged with VC4 |
| VC7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | |
| VC8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | `OfficerMixin` | |
| VC9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | `OfficerMixin` | |
| VC10 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | `Operation.clean()` | covered by the shared period suite (see §10) |
| VC11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | `Operation.save()` | covered by the shared period suite (see §10) |
| VC12 | Balance checked at create (project pays) | `payment_source_fund.can_pay(amount)` | `ValidationError` | `"Insufficient project funds: balance is %(balance)s, cannot refund %(amount)s."` | `Entity.can_pay` | |
| VC13 | Tx entity-type contract | `source.is_project` and `target.is_person` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | `Transaction.create()` | implied by VC1/VC2 (model clean blocks first) |
| VC14 | Tx operation-type allowed | document is `PROJECT_REFUND` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | `Transaction.create()` | implied by VC1/VC2 |
| VC15 | Source ≠ target | project ≠ person | always true | `"Source and target funds must be different."` | `Transaction.clean()` | structural (project ≠ person) |
| VC16 | Destination is active shareholder of source | an active `StakeholderRole.SHAREHOLDER` link exists from the source project to the destination | `ValidationError` | `"The refund destination must be a registered shareholder of the project."` | | |
| VC17 | Refund ≤ net funded by shareholder | `amount <= total_funded − total_refunded` (unreversed `PROJECT_FUNDING` − unreversed `PROJECT_REFUND` for this project↔person pair) | `ValidationError` | `"Refund amount %(amount)s exceeds the net amount funded (%(net_refundable)s) by this shareholder."` | | |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | 1 × `PROJECT_REFUND_ISSUANCE`, amount `== op.amount`, `project → person` | `LinkedIssuanceTransactionMixin.save()` | |
| SC2 | Payment tx created | 1 × `PROJECT_REFUND_PAYMENT`, amount `== op.amount`, `project → person` | `LinkedPaymentTransactionMixin.save()` | same as SC1 |
| SC3 | Tx amounts equal op amount | both txs `amount == op.amount` | transaction creation | |
| SC4 | Tx fund direction | both txs `source=project`, `target=person` | | |
| SC5 | Fully settled immediately | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | `LinkedPaymentTransactionMixin` | |
| SC6 | Project fund ▼ amount | `project.balance` decreases by `amount` | `Entity.balance_at` | |
| SC7 | Shareholder fund ▲ amount | `person.balance` increases by `amount` | `Entity.balance_at` | |
| SC8 | No invoice / no movements | `has_invoice=False`; no invoice items; no movement lines | `has_invoice=False` | config flag (`has_invoice=False`); no ledger/movement machinery in `post_save_tasks` |
| SC9 | Period auto-assigned | `period` = the shareholder's covering period (open period auto-created at entity creation) | `Operation.save()` + `Entity.save()` | covered by shared period suite |
| SC10 | Payables/receivables net zero | immediate tles the issuance → `project.payables == 0`, `shareholder.receivables == 0` | one-shot auto-settlement | |

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | `ReversableModel._validate_can_be_reversed` + view guard | |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | `ReversableModel._validate_can_be_reversed` + view guard | |
| VR3 | No explicit txs to reverse | all txs are implicit (one-shot issuance + payment) | `ValidationError` (would require manual reversal) | `"You can't reverse this object as it has non-reversed transactions…"` | `ReversableModel._requires_transaction_reversal` + `Operation._implicit_reversable_transaction_types` | implied by successful reverse |
| VR4 | No non-reversed adjustments | n/a — Project Refund is not adjustable | never fails | — | `is_adjustable=False` | n/a |
| VR5 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | `operation_reverse_view` | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | `ReversableModel.reverse()` | |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | `ReversableModel.reverse()` | |
| SR3 | Reversal inherits identity | `amount`, `source`, `destination` copied | `ReversableModel._get_reverse_kwargs` | |
| SR4 | Counter-tx for issuance | `person → project`, same amount, same type, `reversal_of=original` | `Transaction.reverse()` | |
| SR5 | Counter-tx for payment | `person → project`, same amount, same type, `reversal_of=original` | same as SR4 | |
| SR6 | Counter-txs preserve type + amount | `counter.type == original.type`, `counter.amount == original.amount` | same as SR4 | |
| SR7 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | `LinkedIssuanceTransactionMixin.save()` | |
| SR8 | Project + shareholder restored | `project.balance` and `person.balance` back to pre-create baseline | `balance_at` | |
| SR9 | Settlement state cleared | `amount_settled == 0`, `is_fully_settled == False` | `amount_settled` | differential invariant; no dedicated focused test yet (see §11) |
| SR10 | Reason flows to reversal | `reversal.description` contains the reason | `ReversableModel.reverse()` | shared engine (see §11 — no dedicated focused test yet) |
| SR11 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger) | whole engine | |
| SR12 | Payables/receivables stay zero | reversal mirrors must not leak into the buckets → both remain `0.00` | one-shot auto-settlement | |

### 5.3 `pay` (one-shot guard)

There is **no standalone pay action** for Project Refund:

| Branch | Behavior | Enforced by | Pinned by test |
|--------|----------|-------------|----------------|
| `process_payment()` called | no-op (returns immediately — `can_pay=False`) | `process_payment` | n/a (covered by `can_pay=False`) |
| `create_payment_transaction()` called after create | `ValidationError` — one-shot allows a single payment only, amount must equal `op.amount` (balance re-checked first, VC12) | `create_payment_transaction` | |

### 5.4 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by `ImmutableMixin` via `_immutable_fields`.

| Branch | Enforced by | Pinned by test |
|--------|-------------|----------------|
| `source` changed after save | `ImmutableMixin.save()` | |
| `destination` changed after save | `ImmutableMixin.save()` | |
| `amount` changed after save | `ImmutableMixin.save()` | |

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — `Entity.save()`.
- The operation's governing entity (`period_entity`) is the **destination shareholder person** (`_dest_role = "url"`) — `Operation.period_entity`.
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC11).
- New operations dated inside a **closed** period are rejected (VC10) — `is_date_in_closed_period`.
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period (`_reverse_period`).

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
| Create route | `POST/GET /<person_pk>/project-refunding/create` → `OperationCreateView` |
| Source selection | a **Project** picked from the secondary field (`_source_role="post"`); `get_related_entities` returns the projects for which the URL person is an active shareholder |
| Destination selection | the **Person (shareholder)** from the URL (`_dest_role="url"`, resolved by `resolve_request`); no picker |
| Category | hidden (no category) |
| Amount | raw `amount` POST field (`_compute_amount`); validated > 0 at model; balance- and cap-checked at create (VC12/VC17) |
| POST parsing | `OperationDataValidator` — date format, description, category (n/a), `amount_paid` (n/a, forced 0) |
| List entry | "Project ReFunding" link (template label text) |
| Detail | `operation_detail_view` — shows the operation total + settlement status + reversal action; the individual issuance/payment transactions are hidden (one-shot — two identical amounts would confuse users) |
| Reverse | `operation_reverse_view` — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

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
| Tx creation + counts | | SC1, SC2 |
| Tx amounts | | SC3 |
| Tx direction | | SC4 |
| Settlement | | SC5 |
| Payables/receivables | | SC10 |
| Source/dest validation | | VC1, VC2 |
| Shareholder check | | VC16 |
| Active entities | | VC3–VC6 |
| Amount | | VC7 |
| Balance check | | VC12 |
| Net-funded cap | | VC17 |
| Officer | | VC8, VC9 |
| Immutability | | IM1–IM3 |
| One-shot guard | | BP2 |
| Project ▼ / shareholder ▲ | | SC6, SC7 |
| Reverse happy path | | SR1–SR3 |
| Counter txs | | SR4–SR7 |
| Reverse constraints | | VR1, VR2 |
| Balance restored | | SR8 |
| Payables/receivables through reversal | | SR12 |
| Differential invariant | | SR11, SR9 |

---
