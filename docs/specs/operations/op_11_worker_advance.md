# Worker Advance — Operation Contract

**Epic:** 12.2 — Repayable Operations
**Type:** One-shot, repayable (`has_repayment=True`, `max_payment_transaction_count=1`)
**Actions:** `create`, `repay`, `reverse`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Worker Advance** operation.
> Every clause below is registered to its implementing code (model → mixin → transaction → view) and to its pinning test.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> Other operations follow the same structure — see [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md).

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.WORKER_ADVANCE` (`"WORKER_ADVANCE"`) | |
| Proxy class | `WorkerAdvanceOperation` | |
| URL slug | `"worker-advance"` | |
| Label | `"Worker Advance Issuance"` | |
| Theme | `danger` / `bi-box-arrow-up-right` (defaults, not overridden) | |
| Source role | `url` (must be a Project) | |
| Destination role | `post` (must be an active Worker) | |
| Registered in | `PROXY_MAP` | |
| Cross-op reference | row WA | [`operations-comparison.md`](operations-comparison.md) |

**Configuration flags**:

| Flag | Value | Meaning |
|------|-------|---------|
| `_issuance_transaction_type` | `WORKER_ADVANCE_ISSUANCE` | issuance (memo) tx created on save |
| `_payment_transaction_type` | `WORKER_ADVANCE_PAYMENT` | payment (cash-out) tx created on save (one-shot) |
| `_repayment_transaction_type` | `WORKER_ADVANCE_REPAYMENT` | repayment tx created via **repay** |
| `is_repayable` | `True` | repayment action enabled |
| `_is_one_shot_operation` | `True` | payment fires at save; no standalone pay action |
| `can_pay` | `False` | `process_payment()` is a no-op |
| `is_partially_payable` | `False` | payment must equal amount (one-shot) |
| `max_payment_transaction_count` | `1` | exactly one payment tx ever |
| `check_balance_on_payment` | `False` | balance enforced in proxy `clean()` at create, not per payment |
| `has_category` / `category_required` | `False` | no financial category |
| `has_repayment` / `repayment_label` | `True` / `"Advance Repayment"` | repay action present |
| `has_invoice` | `False` | no invoice items / no inventory movements |
| `creates_assets` | `False` | no asset creation |

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row links the clause to the code that must honor it.

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_source`/`clean_destination`/`clean` | |
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
| One-shot payment tx creation + settlement (`amount_settled`) | `LinkedPaymentTransactionMixin` |
| Repayment (`amount_repayed`, cap by settled, over-repayment guard) | `LinkedRePaymentTransactionMixin` |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | `ReversableModel` + `Operation.reverse()` |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | |
| `WORKER_ADVANCE_ISSUANCE` (project → worker, non-cash) | |
| `WORKER_ADVANCE_PAYMENT` (project → worker, affects balance) | |
| `WORKER_ADVANCE_REPAYMENT` (worker → project, affects balance) | |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Balance derived from payment-type txs (`WORKER_ADVANCE_PAYMENT`, `WORKER_ADVANCE_REPAYMENT`) | `Entity.balance_at` |
| Payables / receivables derivation | `Entity.payables_at`, `Entity.receivables_at` |
| Real (non-virtual) funds balance-checked | `Entity.can_pay` |
| Open financial period auto-created on entity creation | `Entity.save()` |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (generic, URL source + secondary-entity destination picker) | `OperationCreateView` |
| POST parsing/validation | `OperationDataValidator` |
| Repay view | `record_transaction_repayment` |
| Reverse view (reason required) | `operation_reverse_view` |
| Detail view (aggregate amount + outstanding balance + repay/reverse buttons; per-transaction list hidden — one-shot) | `operation_detail_view` |
| URL: `/<pk>/worker-advance/create` | |
| URL: `repayment/<pk>/create` | |
| URL: `/<pk>/detail/` | |
| URL: `/<pk>/reverse/` | |
| Templates | |

### 2.6 Tests

| Concern | Test file |
|---------|-----------|
| Create branches (one-shot pair, validation, immutability) | |
| Repay branches | |
| Reverse branches | |
| Coverage manifest (executable branch registry) | |

---

## 3. Money flow & entities

- **Source (project / payer):** the **Project** entity in the URL (`_source_role="url"`). Its fund is the payment source fund — a **real, balance-checked** fund (VC11).
- **Destination (worker / receiver):** a **Person** (`is_person=True`) that is an **active `WORKER` stakeholder** of the source project, selected via the POST secondary-entity field (`_dest_role="post"`, `get_related_entities`). Its fund is the payment target fund.
- **Transaction flow:**

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `WORKER_ADVANCE_ISSUANCE` | `project.fund → worker.fund` | none (issuance, non-cash memo) |
| 2 | `WORKER_ADVANCE_PAYMENT` | `project.fund → worker.fund` | ▼ project fund, ▲ worker fund, ▲ project receivables, ▲ worker payables |
| 3 | `WORKER_ADVANCE_REPAYMENT` | `worker.fund → project.fund` | ▲ project fund, ▼ worker fund, ▼ project receivables, ▼ worker payables |

- **Payment source fund:** `self.source` (project)
- **Payment target fund:** `self.destination` (worker)
---

## 4. Settlement model

### 4.1 Payment settlement (one-shot at create)

Derived from `LinkedPaymentTransactionMixin` using `WORKER_ADVANCE_PAYMENT` only:

| Property | After create | After reverse |
|----------|--------------|---------------|
| `amount_settled` | `== amount` | `0.00` |
| `total_settlable_amount` (`effective_amount`) | `== amount` | unchanged |
| `amount_remaining_to_settle` | `0.00` | `== amount` |
| `is_fully_settled` | `True` | `False` |

Because the operation is **one-shot**, the payment fires on save — settlement is **immediate at create** (unlike the multi-stage Loan, there is no separate pay step).

### 4.2 Repayment model

Derived from `LinkedRePaymentTransactionMixin` using `WORKER_ADVANCE_REPAYMENT` only:

| Property | Formula / behavior | Defined in |
|----------|--------------------|-----------|
| `repayable_amount` | `min(total_repayable_amount, amount_settled)` — `== amount` from create (payment already fired) | |
| `amount_repayed` | net `WORKER_ADVANCE_REPAYMENT` flow toward the project fund (reversals netted out) | |
| `amount_remaining_to_repay` | `repayable_amount − amount_repayed` | |
| `is_fully_repayed` | `amount_repayed >= repayable_amount` | |

**Key rule:** unlike a Loan, the Worker Advance is **repayable immediately after create** — the one-shot payment fires on save, so `amount_settled == amount` and therefore `repayable_amount == amount` from the start. Repayments can never exceed the advance amount, and once fully repayed the operation is terminal.

---

## 5. Actions

### 5.1 `create`

Entry points: model `WorkerAdvanceOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx, then one-shot payment tx).

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source (project) is a Project | `source.is_project` | `ValidationError` | `"Worker advance source should be a project."` | `clean_source` | |
| VC2 | Destination (worker) is a Person | `destination.is_person` | `ValidationError` | `"Worker Advance destination must be a person entity."` | `clean_destination` | |
| VC3 | Destination is an active `WORKER` stakeholder of the source project | active `Stakeholder(parent=source, target=dest, role=WORKER)` exists | `ValidationError` | `"Worker Advance destination must be an active worker in the selected project."` | `clean_destination` | |
| VC4 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | `Operation.clean()` | |
| VC5 | Destination entity active | `destination.active` | `ValidationError` | same as VC4 | `Operation.clean()` | |
| VC6 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | `SourceFundMixin` | merged with VC4 |
| VC7 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | `TargetFundMixin` | merged with VC5 |
| VC8 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | |
| VC9 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | `OfficerMixin` | |
| VC10 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | `OfficerMixin` | |
| VC11 | Project fund has sufficient balance | `payment_source_fund.can_pay(amount)` | `ValidationError` | `"Insufficient funds: project fund balance (%(balance)s) is less than the advance amount (%(amount)s)."` | `WorkerAdvanceOperation.clean()` | |
| VC12 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | `Operation.clean()` | covered by period suite |
| VC13 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | `Operation.save()` | covered by period suite |
| VC14 | Tx entity-type contract | `source.is_project` and `target.is_worker` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | `Transaction.create()` | implied by VC1–VC3 (model clean blocks first) |
| VC15 | Tx operation-type allowed | document is `WORKER_ADVANCE` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | `Transaction.create()` | implied by VC1–VC3 |
| VC16 | Source ≠ destination | `source_id != destination_id` | `ValidationError` | `"Source and target funds must be different."` | `Transaction.clean()` | structural (project ≠ person) |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | 1 × `WORKER_ADVANCE_ISSUANCE`, amount `== op.amount`, `project → worker` (non-cash memo) | `LinkedIssuanceTransactionMixin.save()` | |
| SC2 | Payment tx created | 1 × `WORKER_ADVANCE_PAYMENT`, amount `== op.amount`, `project → worker` | `LinkedPaymentTransactionMixin.save()` | |
| SC3 | Exactly two txs | one-shot pattern writes issuance + payment, nothing else | one-shot `post_save_tasks` | |
| SC4 | Project fund ▼ amount | `project.balance` decreases by `amount` | `Entity.balance_at` | |
| SC5 | Worker fund ▲ amount | `worker.balance` increases by `amount` | `Entity.balance_at` | |
| SC6 | Project receivables ▲ amount | the advance is a receivable the project is owed | `Entity.receivables_at` | |
| SC7 | Worker payables ▲ amount | the worker now owes the advance back | `Entity.payables_at` | |
| SC8 | Project payables unchanged | no payable created for the project | `payables_at` | |
| SC9 | Worker receivables unchanged | no receivable created for the worker | `receivables_at` | |
| SC10 | Repayment-tracked from create | `amount_remaining_to_repay == op.amount` after create | `repayable_amount` / `amount_repayed` | |
| SC11 | One-shot guard | a second payment tx is rejected | `create_payment_transaction()` | |

### 5.2 `repay`

Entry point: model `op.create_repayment_transaction(amount, officer, date)` or view `record_transaction_repayment` (`POST repayment/<pk>/create`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VRp1 | Amount > 0 | `amount > 0` | `ValidationError` | `"The amount should be more than 0"` | `validate_repayement_amount` | |
| VRp2 | Amount ≤ remaining | `amount <= amount_remaining_to_repay` | `ValidationError` | `"The paid amount %(amount)s exceeds the remaining: %(remaining)s"` | `validate_repayement_amount` | |
| VRp3 | Closed-period guard on repayment date | governing period open on `date` | `ValidationError` | `"Cannot record a repayment dated within a closed financial period."` | `create_repayment_transaction()` | covered by period suite |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SRp1 | `WORKER_ADVANCE_REPAYMENT` created | `worker.fund → project.fund`, type `WORKER_ADVANCE_REPAYMENT`, amount exact | `create_repayment_transaction()` | |
| SRp2 | Exactly one repayment per call | issuance + payment + exactly one repayment | `Transaction.create` | |
| SRp3 | Worker fund ▼ amount | `worker.balance` decreases by `amount` | `Entity.balance_at` | |
| SRp4 | Project fund ▲ amount | `project.balance` increases by `amount` | `Entity.balance_at` | |
| SRp5 | Project receivables ▼ | `project.receivables` decreases by `amount` | `receivables_at` | |
| SRp6 | Worker payables ▼ | `worker.payables` decreases by `amount` | `payables_at` | |
| SRp7 | `amount_remaining_to_repay` ▼ | remaining decreases by `amount` | `amount_remaining_to_repay` | |
| SRp8 | Multiple partial repayments accumulate | remaining sums all active repayments | `amount_repayed` | |
| SRp9 | Full repayment → `is_fully_repayed` | `amount_repayed == repayable_amount`, remaining `0` | `is_fully_repayed` | |
| SRp10 | Full repayment zeroes project receivables | `project.receivables == 0` | `receivables_at` | |
| SRp11 | Full repayment zeroes worker payables | `worker.payables == 0` | `payables_at` | |
| SRp12 | Differential invariant (repay + reverse) | repay then reverse the repayment returns to the advance-only state | whole engine | |

### 5.3 Individual transaction reversal (repay)

The **operation-level** reverse is distinct from reversing an individual `WORKER_ADVANCE_REPAYMENT` transaction.

| # | Branch | Behavior | Enforced by | Pinned by test |
|---|--------|----------|-------------|----------------|
| TR1 | Repayment tx reversed | `amount_repayed` ↓, `is_fully_repayed` unset, `amount_remaining_to_repay` restored; worker ▲, project ▼; worker payables ▲, project receivables ▲ | `Transaction.reverse()` | |
| TR2 | Reversed repayment must not leak into the opposite bucket | the reversal mirror must not create a payable for the project | obligation derivation | |

### 5.4 `reverse` (operation level)

Entry point: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.4.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | `ReversableModel._validate_can_be_reversed` + view guard | |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | `ReversableModel._validate_can_be_reversed` + view guard | |
| VR3 | No outstanding repayments | no active non-reversed `WORKER_ADVANCE_REPAYMENT` tx | `ValidationError` | `"You can't reverse this object as it has non-reversed transactions…"` | `WorkerAdvanceOperation._requires_transaction_reversal()` + `ReversableModel._requires_transaction_reversal` | |
| VR4 | No explicit txs to reverse | all txs are implicit (one-shot issuance + payment) | `ValidationError` (would require manual reversal) | `"You can't reverse this object as it has non-reversed transactions…"` | `_implicit_reversable_transaction_types` | implied by successful reverse |
| VR5 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | `operation_reverse_view` | view contract (see §8) |

#### 5.4.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | `ReversableModel.reverse()` | |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | `ReversableModel.reverse()` | |
| SR3 | Reversal is a reversal, not reversed | `reversal.is_reversal`, `not reversal.is_reversed` | `ReversableModel` | |
| SR4 | Reversal inherits identity | `amount`, `source`, `destination` copied | `ReversableModel._get_reverse_kwargs` | |
| SR5 | Counter-tx for issuance + payment | both implicit types get counter-txs, `worker → project`, same amounts, `reversal_of=original` | `_implicit_reversable_transaction_types` | |
| SR6 | Counter-txs flip funds | `counter.source = original.target`, `counter.target = original.source`, same amount | `Transaction.reverse()` | |
| SR7 | Project fund restored | `project.balance` back to pre-create baseline | `balance_at` | |
| SR8 | Worker fund restored | `worker.balance` back to `0.00` | `balance_at` | |
| SR9 | Project receivables restored | `project.receivables == 0` | `receivables_at` | |
| SR10 | Worker payables restored | `worker.payables == 0` | `payables_at` | |
| SR11 | Project payables unchanged | no payable leak | `payables_at` | |
| SR12 | Worker receivables unchanged | no receivable leak | `receivables_at` | |
| SR13 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger) | whole engine | |

### 5.5 `pay` (one-shot guard)

There is **no standalone pay action** for Worker Advance — the payment is part of the one-shot create:

| Branch | Behavior | Enforced by | Pinned by test |
|--------|----------|-------------|----------------|
| `process_payment()` called | no-op (returns immediately — `can_pay=False`) | `process_payment` | n/a (covered by `can_pay=False`) |
| `create_payment_transaction()` called after create | `ValidationError` — one-shot allows a single payment only, amount must equal `op.amount` | `create_payment_transaction()` | |

### 5.6 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by `ImmutableMixin` via `_immutable_fields`.

| Branch | Enforced by | Pinned by test |
|--------|-------------|----------------|
| `source` changed after save | `ImmutableMixin.save()` | |
| `destination` changed after save | `ImmutableMixin.save()` | |
| `amount` changed after save | `ImmutableMixin.save()` | |

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — `Entity.save()`.
- The operation's governing entity (`period_entity`) is the **source project** (`_source_role = "url"`) — `Operation.period_entity`.
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC13).
- New operations dated inside a **closed** period are rejected (VC12) — `is_date_in_closed_period`.
- **Repay** transactions are also rejected if dated inside a closed period of the governing entity (VRp3).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period (`_reverse_period`).

---

## 7. Entity roles & balance contract

- The source must be a **Project**; the destination must be a **Person** that is an **active `WORKER` stakeholder** of the source project — enforced at model (VC1–VC3) and transaction (VC14/VC15) layers.
- `project.balance` / `worker.balance` are derived exclusively from **payment-type** transactions (`WORKER_ADVANCE_PAYMENT`, `WORKER_ADVANCE_REPAYMENT`); the issuance tx (`WORKER_ADVANCE_ISSUANCE`) never moves a balance.
- **Payment (`WORKER_ADVANCE_PAYMENT`)** increases project receivables and worker payables (the obligation); **repayment (`WORKER_ADVANCE_REPAYMENT`)** decreases them. Reversals restore them without leaking into the opposite bucket (SR9–SR12, TR2).
- The project is a **real internal payer**, so its fund is **balance-checked at create** (VC11) via the proxy `clean()`; `check_balance_on_payment=False` because there is no standalone pay step.

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Create route | `POST/GET /<project_pk>/worker-advance/create` → `OperationCreateView` |
| Source selection | locked to the URL entity — the **Project** (`_source_role="url"`) |
| Destination selection | secondary-entity picker (`_dest_role="post"`) — active `WORKER` stakeholders of the URL project, via `get_related_entities` |
| Category | hidden (no category) |
| Amount | raw `amount` POST field (`_compute_amount`); validated > 0 at model; project balance checked at create (VC11) |
| POST parsing | `OperationDataValidator` — date format, description, category (n/a), `amount_paid` (n/a, forced 0) |
| List entry | "Worker Advance" link |
| Detail | `operation_detail_view` — shows the advance amount, total repaid so far, outstanding balance to repay, Record Repayment / Reverse buttons; the individual issuance/payment transactions are hidden (one-shot — two identical amounts would confuse users) |
| Repay | `repayment/<pk>/create` → `record_transaction_repayment` — `PaymentForm`, `can_repay` guard, shows `amount_remaining_to_repay`, blocks over-repayment (VRp2) |
| Reverse | `/<pk>/reverse/` → `operation_reverse_view` — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source=project · VC2 dest=person · VC3 dest=active worker stakeholder · VC4 source active · VC5 dest active · VC6 source fund active · VC7 target fund active · VC8 amount>0 · VC9 officer staff · VC10 officer active · VC11 project balance at create · VC12 not closed-period · VC13 covering period exists · VC14 tx entity-type (project→worker) · VC15 tx op-type (WorkerAdvance) · VC16 source≠dest

**create — effects:** SC1 issuance tx · SC2 payment tx · SC3 exactly two txs · SC4 project ▼ · SC5 worker ▲ · SC6 project receivables ▲ · SC7 worker payables ▲ · SC8 project payables unchanged · SC9 worker receivables unchanged · SC10 repayment-tracked from create · SC11 one-shot guard

**repay — validation:** VRp1 amount>0 · VRp2 amount≤remaining · VRp3 not closed-period

**repay — effects:** SRp1 `WORKER_ADVANCE_REPAYMENT` created · SRp2 exactly one · SRp3 worker ▼ · SRp4 project ▲ · SRp5 project receivables ▼ · SRp6 worker payables ▼ · SRp7 remaining ▼ · SRp8 multiple accumulate · SRp9 fully repayed · SRp10 receivables zeroed · SRp11 payables zeroed · SRp12 differential invariant

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no outstanding repayments · VR4 no explicit txs · VR5 reason required (view)

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 is reversal · SR4 identity copied · SR5 issuance+payment counter-txs · SR6 funds flipped · SR7 project restored · SR8 worker restored · SR9 receivables restored · SR10 payables restored · SR11 project payables unchanged · SR12 worker receivables unchanged · SR13 differential invariant

**tx reversal / immutability:** TR1 repayment reversed → repaid state restored · TR2 reversed repayment no bucket leak · BP1 `process_payment` no-op · BP2 `create_payment_transaction` blocked after create · IM1/IM2/IM3 source/destination/amount immutable

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| Issuance tx | | SC1 |
| Payment tx | | SC2 |
| Exactly two txs | | SC3 |
| Fund balances | | SC4, SC5 |
| Obligation buckets | | SC6–SC9 |
| Repayment-tracked | | SC10 |
| One-shot guard | | SC11, BP2 |
| Source validation | | VC1, VC4, VC11 |
| Destination validation | | VC2, VC3, VC5 |
| Amount | | VC8 |
| Officer | | VC9, VC10 |
| Immutability | | IM1–IM3 |
| Balance check flag | | VC11 (via clean) |
| Repayment tx | | SRp1, SRp2 |
| Repay balances | | SRp3, SRp4 |
| Repay buckets | | SRp5, SRp6, SRp10, SRp11 |
| Derived amounts | | SRp7–SRp9 |
| Over-repayment guard | | VRp2, VRp1 |
| Repayment reversal restores state | | TR1 |
| Reversed repayment buckets | | TR2 |
| Repay differential | | SRp12, TR1 |
| Reverse happy path | | SR1–SR4 |
| Counter-txs | | SR5, SR6 |
| Reverse balances | | SR7, SR8 |
| Reverse buckets | | SR9–SR12 |
| Reverse differential | | SR13 |
| Reverse blocked by repayment | | VR3 |
| Reverse constraints | | VR1, VR2 |

---

## 11. Tasks

- [x] Verify issuance transaction created correctly (project → worker, type `WORKER_ADVANCE_ISSUANCE`)
- [x] Verify payment transaction created on save (project → worker, type `WORKER_ADVANCE_PAYMENT`) — one-shot pair
- [x] Verify exactly two transactions are created at create
- [x] Verify source must be a Project entity (VC1)
- [x] Verify destination must be a Person entity (VC2)
- [x] Verify destination must be an active `WORKER` stakeholder of the source project (VC3)
- [x] Verify both entities must be `active=True` (VC4, VC5)
- [x] Verify source fund must be `active=True` (VC6)
- [x] Verify project fund balance is sufficient at create (VC11)
- [x] Verify amount must be positive (VC8)
- [x] Verify officer must be staff + active (VC9, VC10)
- [x] Verify immutability of `source`, `destination`, `amount` after save (IM1–IM3)
- [x] Verify project fund balance decreases and worker fund balance increases by the advance amount
- [x] Verify project receivables increase and worker payables increase (obligation created)
- [x] Verify project payables and worker receivables stay unchanged
- [x] Verify `amount_remaining_to_repay` equals the full amount after creation
- [x] Verify `create_payment_transaction()` is blocked after creation (one-shot)
- [x] Verify repayment transaction direction: `worker.fund → project.fund`, type `WORKER_ADVANCE_REPAYMENT`
- [x] Verify multiple partial repayments are allowed and accumulate
- [x] Verify over-repayment is rejected (VRp1, VRp2)
- [x] Verify full repayment marks the operation as fully repayed and zeroes receivables/payables
- [x] Verify reversing a repayment restores derived amounts and buckets without leaking (TR1, TR2)
- [x] Verify reversal is blocked if any repayment exists (VR3)
- [x] Verify reversal creates counter-transactions for both issuance and payment (SR5, SR6)
- [x] Verify project & worker funds and obligation buckets restored after reversal (SR7–SR12)
- [x] Verify reversal marks the operation as reversed, sets `reversed_by`, and marks `is_reversal` (SR1–SR3)
- [x] Verify reversal inherits amount, source, destination from original (SR4)
- [x] Verify cannot reverse an already-reversed operation or a reversal (VR1, VR2)
- [x] UI: create form — source restricted to Projects, destination filtered to active workers of the selected project
- [x] UI: detail view shows advance amount, total repaid so far, outstanding balance, and "Record Repayment" button
- [x] UI: repayment form shows the remaining balance (`amount_remaining_to_repay`) for reference while leaving the amount field blank for user entry; over-repayment is blocked (VRp2) — the field is intentionally not pre-filled
- [ ] Add a focused test for the operation **closed-period** create guard (VC12/VC13) specific to Worker Advance
