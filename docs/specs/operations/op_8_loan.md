# Loan — Operation Contract

**Epic:** 12.1 — Repayable Operations
**Type:** Multi-stage, repayable (`has_repayment=True`, `max_payment_count=-1`)
**Actions:** `create`, `pay`, `repay`, `reverse`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Loan** operation.
> Every clause below is registered to its implementing code (model → mixin → transaction → view) and to its pinning test.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> Other operations follow the same structure — see [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md).

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.LOAN` (`"LOAN"`) | |
| Proxy class | `LoanOperation` | |
| URL slug | `"loan"` | |
| Label | `"Debt Issuance"` | |
| Theme | `danger` / `bi-box-arrow-up-right` (defaults, not overridden) | |
| Source role | `url` (must be a Person or Project) | |
| Destination role | `post` (must be a Person or Project) | |
| Registered in | `PROXY_MAP` | |
| Cross-op reference | row LN | [`operations-comparison.md`](operations-comparison.md) |

**Configuration flags**:

| Flag | Value | Meaning |
|------|-------|---------|
| `_issuance_transaction_type` | `LOAN_ISSUANCE` | issuance (memo) tx created on save |
| `_payment_transaction_type` | `LOAN_PAYMENT` | disbursement tx created via **pay** (not on save) |
| `_repayment_transaction_type` | `LOAN_REPAYMENT` | repayment tx created via **repay** |
| `is_repayable` | `True` | repayment action enabled |
| `_is_one_shot_operation` | `False` | multi-stage: no payment at save; standalone pay action |
| `can_pay` | `False` | `process_payment()` is a no-op; payments created standalone |
| `is_partially_payable` | `False` | settlement driven by remaining; not a one-shot equality |
| `max_payment_transaction_count` | `-1` | unlimited partial disbursements |
| `check_balance_on_payment` | `True` | each disbursement is balance-checked at pay time |
| `has_category` / `category_required` | `False` | no financial category |
| `has_repayment` / `repayment_label` | `True` / `"Loan Recovery"` | repay action present |
| `has_invoice` | `False` | no invoice items / no inventory movements |
| `is_adjustable` | `False` | no accounting adjustment action |

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
| Disbursement / settlement (`amount_settled`, balance check per payment) | `LinkedPaymentTransactionMixin` |
| Repayment (`amount_repayed`, cap by disbursed, over-repayment guard) | `LinkedRePaymentTransactionMixin` |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | `ReversableModel` + `Operation.reverse()` |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | |
| `LOAN_ISSUANCE` (creditor → debtor, non-cash) | |
| `LOAN_PAYMENT` (creditor → debtor, affects balance) | |
| `LOAN_REPAYMENT` (debtor → creditor, affects balance) | |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Balance derived from payment-type txs (`LOAN_PAYMENT`, `LOAN_REPAYMENT`) | `Entity.balance_at` |
| Real (non-virtual) funds balance-checked | `Entity.can_pay` |
| Open financial period auto-created on entity creation | `Entity.save()` |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (generic, URL source + secondary-entity destination picker) | `OperationCreateView` |
| POST parsing/validation | `OperationDataValidator` |
| Pay view (disbursement) | `record_transaction_payment` |
| Repay view | `record_transaction_repayment` |
| Reverse view (reason required) | `operation_reverse_view` |
| Detail view (transactions + outstanding balance + pay/repay/reverse buttons) | `operation_detail_view` |
| URL: `/<pk>/loan/create` | |
| URL: `payment/<pk>/create` | |
| URL: `repayment/<pk>/create` | |
| URL: `/<pk>/detail/` | |
| URL: `/<pk>/reverse/` | |
| Templates | |

### 2.6 Tests

| Concern | Test file |
|---------|-----------|
| Create branches (issuance, validation, immutability) | |
| Pay (disbursement) branches | |
| Repay branches | |
| Reverse branches | |
| Coverage manifest (executable branch registry) | |

---

## 3. Money flow & entities

- **Source (creditor / payer):** the **Person or Project** entity in the URL (`_source_role="url"`). Its fund is the payment source fund — the real payer for disbursements.
- **Destination (debtor / receiver):** a **Person or Project** entity (`_dest_role="post"` — secondary-entity picker, `get_related_entities`). Its fund is the payment target fund.
- **Transaction flow:**

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `LOAN_ISSUANCE` | `creditor.fund → debtor.fund` | none (issuance, non-cash memo) |
| 2 | `LOAN_PAYMENT` | `creditor.fund → debtor.fund` | ▼ creditor fund, ▲ debtor fund, ▲ creditor receivables, ▲ debtor payables |
| 3 | `LOAN_REPAYMENT` | `debtor.fund → creditor.fund` | ▲ creditor fund, ▼ debtor fund, ▼ creditor receivables, ▼ debtor payables |

- **Payment source fund:** `self.source` (creditor)
- **Payment target fund:** `self.destination` (debtor)
> **World / System exclusion.** The World and System entities can never be a side of a loan: both `clean_source()` and `clean_destination()` require Person or Project, and the transaction uses `not_virtual` for both sides.

---

## 4. Settlement model

### 4.1 Payment settlement (disbursements)

Derived from `LinkedPaymentTransactionMixin` using `LOAN_PAYMENT` only:

| Property | After create | After each pay | After full pay |
|----------|--------------|----------------|----------------|
| `amount_settled` | `0.00` | `∑ LOAN_PAYMENT` | `== amount` |
| `total_settlable_amount` | `== amount` | unchanged | unchanged |
| `amount_remaining_to_settle` | `== amount` | `amount − settled` | `0.00` |
| `is_fully_settled` | `False` | depends | `True` |

### 4.2 Repayment model

Derived from `LinkedRePaymentTransactionMixin` using `LOAN_REPAYMENT` only:

| Property | Formula / behavior | Defined in |
|----------|--------------------|-----------|
| `repayable_amount` | `min(total_repayable_amount, amount_settled)` — capped by the disbursed amount | |
| `amount_repayed` | net `LOAN_REPAYMENT` flow toward the creditor fund (reversals netted out) | |
| `amount_remaining_to_repay` | `repayable_amount − amount_repayed` | |
| `is_fully_repayed` | `amount_repayed >= repayable_amount` | |

**Key rule:** a loan with **no disbursement** is not repayable — `repayable_amount` is `0` because `amount_settled` is `0`. Repayments can never exceed the total disbursed (`∑ LOAN_PAYMENT`), even if the loan agreement (`amount`) is larger.

---

## 5. Actions

### 5.1 `create`

Entry points: model `LoanOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx only — no payment).

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source (creditor) is Person or Project | `source.is_person or source.is_project` | `ValidationError` | `"Loan source (creditor) must be a Person or Project entity."` | `clean_source` | |
| VC2 | Destination (debtor) is Person or Project | `destination.is_person or destination.is_project` | `ValidationError` | `"Loan destination (debtor) must be a Person or Project entity."` | `clean_destination` | |
| VC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | `Operation.clean()` | |
| VC4 | Destination entity active | `destination.active` | `ValidationError` | same as VC3 | `Operation.clean()` | |
| VC5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | `SourceFundMixin` | merged with VC3 |
| VC6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | `TargetFundMixin` | merged with VC4 |
| VC7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | |
| VC8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | `OfficerMixin` | |
| VC9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | `OfficerMixin` | |
| VC10 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | `Operation.clean()` | covered by period suite |
| VC11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | `Operation.save()` | covered by period suite |
| VC12 | Balance exempt at create | issuance is unguarded; balance check deferred to each disbursement | never fails at create | — | `check_balance_on_payment=True` (only at pay) | |
| VC13 | Tx entity-type contract | both sides non-virtual (Person or Project) | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | `Transaction.create()` | implied by VC1/VC2 (model clean blocks first) |
| VC14 | Tx operation-type allowed | document is `LOAN` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | `Transaction.create()` | implied by VC1/VC2 |
| VC15 | Source ≠ destination | `source_id != destination_id` | `ValidationError` | `"Loan source (creditor) and destination (debtor) must be different entities."` | `clean()` | |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | 1 × `LOAN_ISSUANCE`, amount `== op.amount`, `creditor → debtor` (non-cash memo) | `LinkedIssuanceTransactionMixin.save()` | |
| SC2 | Issuance direction | `source=creditor`, `target=debtor` | transaction creation | |
| SC3 | Issuance amount equals op amount | `tx.amount == op.amount` | transaction creation | |
| SC4 | No payment on save | multi-stage: only `LOAN_ISSUANCE` exists; disbursements happen later via **pay** | `_is_one_shot_operation=False` | (asserts only `LOAN_ISSUANCE: 1`) |
| SC5 | No balance effect at create | issuance is a non-payment type; no fund/receivable/payable change | issuance_types (`LOAN_ISSUANCE`) | module contract |
| SC6 | Not repayable before disbursement | `amount_remaining_to_repay == 0` with no `LOAN_PAYMENT` | `repayable_amount` cap | |
| SC7 | `creditor`/`debtor` aliases | `creditor == source`, `debtor == destination` | | |
| SC8 | Person or Project allowed on either side | any combination of Person/Project accepted | `clean_source`/`clean_destination` | |

### 5.2 `pay` (disbursement)

Entry point: model `op.create_payment_transaction(amount, officer, date)` or view `record_transaction_payment` (`POST payment/<pk>/create`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VP1 | Balance enforced per disbursement | `payment_source_fund.can_pay(amount)` | `ValidationError` | `"Insufficient funds: fund balance (%(balance)s) is less than the payment amount (%(amount)s)."` | `create_payment_transaction()` | |
| VP2 | Amount > 0 | `amount > 0` | `ValidationError` | `"The amount should be more than 0"` | `validate_settlement_amount` | n/a (shared engine) |
| VP3 | Amount ≤ remaining | `amount <= amount_remaining_to_settle` | `ValidationError` | `"The paid amount %(amount)s exceeds the remaining: %(remaining)s"` | `validate_settlement_amount` | over-payment guard (shared engine) |
| VP4 | Partial disbursements allowed | unlimited (`max_payment_transaction_count=-1`) | never fails | — | | |
| VP5 | Closed-period guard on payment date | governing period open on `date` | `ValidationError` | `"Cannot record a payment dated within a closed financial period."` | `create_payment_transaction()` | covered by period suite |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SP1 | `LOAN_PAYMENT` created | `creditor.fund → debtor.fund`, type `LOAN_PAYMENT` | `create_payment_transaction()` | |
| SP2 | Payment direction | `source=creditor`, `target=debtor` | payment source/target funds | |
| SP3 | Creditor fund ▼ amount | `creditor.balance` decreases by `amount` | `Entity.balance_at` | |
| SP4 | Debtor fund ▲ amount | `debtor.balance` increases by `amount` | `Entity.balance_at` | |
| SP5 | Debtor payables ▲ | `debtor.payables` increases by `amount` | payables derivation | |
| SP6 | Creditor receivables ▲ | `creditor.receivables` increases by `amount` | receivables derivation | |
| SP7 | Other obligation buckets zero | creditor payables & debtor receivables stay `0` | obligation derivation | |
| SP8 | `amount_settled` ↑ | settlement grows by the disbursed amount | `amount_settled` | implied by SP3/SP4 + coverage manifest SE3/SE4 |

### 5.3 `repay`

Entry point: model `op.create_repayment_transaction(amount, officer, date)` or view `record_transaction_repayment` (`POST repayment/<pk>/create`).

#### 5.3.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VRp1 | Amount > 0 | `amount > 0` | `ValidationError` | `"The amount should be more than 0"` | `validate_repayement_amount` | |
| VRp2 | Amount ≤ remaining | `amount <= amount_remaining_to_repay` | `ValidationError` | `"The paid amount %(amount)s exceeds the remaining: %(remaining)s"` | `validate_repayement_amount` | |
| VRp3 | Capped by disbursed amount | `amount <= repayable_amount == min(total, amount_settled)` | `ValidationError` | same as VRp2 | `repayable_amount` | |
| VRp4 | Closed-period guard on repayment date | governing period open on `date` | `ValidationError` | `"Cannot record a repayment dated within a closed financial period."` | `create_repayment_transaction()` | covered by period suite |

#### 5.3.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SRp1 | `LOAN_REPAYMENT` created | `debtor.fund → creditor.fund`, type `LOAN_REPAYMENT` | `create_repayment_transaction()` | |
| SRp2 | Repayment direction | `source=debtor`, `target=creditor` | repayment source/target funds | |
| SRp3 | Debtor fund ▼ amount | `debtor.balance` decreases by `amount` | `Entity.balance_at` | |
| SRp4 | Creditor fund ▲ amount | `creditor.balance` increases by `amount` | `Entity.balance_at` | |
| SRp5 | Debtor payables ▼ | `debtor.payables` decreases by `amount` | payables derivation | |
| SRp6 | Creditor receivables ▼ | `creditor.receivables` decreases by `amount` | receivables derivation | |
| SRp7 | `amount_remaining_to_repay` ▼ | remaining decreases by `amount` | `amount_remaining_to_repay` | |
| SRp8 | Multiple repayments accumulate | remaining sums all active repayments | `amount_repayed` | |
| SRp9 | Full repayment → `is_fully_repayed` | `amount_repayed == repayable_amount`, remaining `0` | `is_fully_repayed` | |
| SRp10 | Differential invariant (repay + reverse) | repay then reverse the repayment returns to the advance-only state | whole engine | |

### 5.4 Individual transaction reversal (pay / repay)

The **operation-level** reverse is distinct from reversing an individual `LOAN_PAYMENT` or `LOAN_REPAYMENT` transaction.

| # | Branch | Behavior | Enforced by | Pinned by test |
|---|--------|----------|-------------|----------------|
| TR1 | Repayment tx reversed | `amount_repayed` ↓, `is_fully_repayed` unset, `amount_remaining_to_repay` restored; debtor ▲, creditor ▼; debtor payables ▲, creditor receivables ▲ | `Transaction.reverse()` | |
| TR2 | Payment tx reversed | returns balance to creditor, decreases debtor; debtor payables ▼, creditor receivables ▼ | `Transaction.reverse()` | engine-level (shared) |
| TR3 | Asymmetric reversal allowed | reversing more payment txs than repayments is allowed — can introduce inconsistency (negative receivables/payables are permitted) | engine-level | documented behavior |

### 5.5 `reverse` (operation level)

Entry point: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.5.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | `ReversableModel._validate_can_be_reversed` + view guard | |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | `ReversableModel._validate_can_be_reversed` + view guard | |
| VR3 | No non-reversed disbursements | no active `LOAN_PAYMENT` tx | `ValidationError` | `"You can't reverse this object as it has non-reversed transactions…"` | `ReversableModel._requires_transaction_reversal` + `_reversable_transaction_types` | |
| VR4 | No outstanding repayments | no active `LOAN_REPAYMENT` tx | `ValidationError` | same as VR3 | `_requires_transaction_reversal()` | |
| VR5 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | `operation_reverse_view` | view contract (see §8) |

#### 5.5.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | `ReversableModel.reverse()` | |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | `ReversableModel.reverse()` | |
| SR3 | Reversal is a reversal, not reversed | `reversal.is_reversal`, `not reversal.is_reversed` | `ReversableModel` | |
| SR4 | Reversal inherits identity | `amount`, `source`, `destination` copied | `ReversableModel._get_reverse_kwargs` | |
| SR5 | Counter-tx for issuance only | 1 × reversed `LOAN_ISSUANCE`; payments/repayments must be cleared manually | `_implicit_reversable_transaction_types` | |
| SR6 | Counter-tx flips funds | `counter.source = original.target`, `counter.target = original.source`, same amount | `Transaction.reverse()` | |
| SR7 | Obligations remain zero | issuance reversal creates no payables/receivables | obligation derivation | |
| SR8 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger) | whole engine | |

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
- The operation's governing entity (`period_entity`) is the **source creditor** (`_source_role = "url"`) — `Operation.period_entity`.
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC11).
- New operations dated inside a **closed** period are rejected (VC10) — `is_date_in_closed_period`.
- **Pay and repay** transactions are also rejected if dated inside a closed period of the governing entity (VP5, VRp4).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period (`_reverse_period`).

---

## 7. Entity roles & balance contract

- Both sides must be **non-virtual** Person or Project entities — enforced at model (VC1/VC2/VC15) and transaction (VC13 `not_virtual`/`not_virtual`) layers. **World and System can never participate** in a loan.
- `creditor.balance` / `debtor.balance` are derived exclusively from **payment-type** transactions (`LOAN_PAYMENT`, `LOAN_REPAYMENT`); the issuance tx (`LOAN_ISSUANCE`) never moves a balance.
- **Disbursement (`LOAN_PAYMENT`)** increases debtor payables and creditor receivables; **repayment (`LOAN_REPAYMENT`)** decreases them. The issuance itself creates no obligations.
- The creditor is a real payer, so each disbursement is **balance-checked** (VP1); the loan issuance itself is deliberately unguarded (VC12).

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Create route | `POST/GET /<entity_pk>/loan/create` → `OperationCreateView` |
| Source selection | locked to the URL entity — the **creditor** (`_source_role="url"`) |
| Destination selection | secondary-entity picker (`_dest_role="post"`) — Person/Project list excluding the URL entity, via `get_related_entities` |
| Category | hidden (no category) |
| Amount | raw `amount` POST field (`_compute_amount`); validated > 0 at model |
| POST parsing | `OperationDataValidator` — date format, description, category (n/a) |
| List entry | "Debt Issuance" link |
| Detail | `operation_detail_view` — shows issuance + disbursements + repayments, outstanding balance to pay and to repay, over-repayment indicator, Record Payment / Record Repayment / Reverse buttons |
| Pay | `payment/<pk>/create` → `record_transaction_payment` — `PaymentForm`, balance enforced (VP1), shows `amount_remaining_to_settle` |
| Repay | `repayment/<pk>/create` → `record_transaction_repayment` — `PaymentForm`, `can_repay` guard, shows `amount_remaining_to_repay`, blocks over-repayment |
| Reverse | `/<pk>/reverse/` → `operation_reverse_view` — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source person| project · VC2 dest person |project · VC3 source active · VC4 dest active · VC5 source fund active · VC6 target fund active · VC7 amount>0 · VC8 officer staff · VC9 officer active · VC10 not closed-period · VC11 covering period exists · VC12 balance exempt at create · VC13 tx entity-type (non-virtual both) · VC14 tx op-type (Loan) · VC15 source≠dest

**create — effects:** SC1 issuance tx · SC2 direction creditor→debtor · SC3 amount matches · SC4 no payment at save · SC5 no balance effect · SC6 not repayable pre-disbursement · SC7 creditor/debtor aliases · SC8 person|project either side

**pay — validation:** VP1 balance per disbursement · VP2 amount>0 · VP3 amount≤remaining · VP4 partial allowed · VP5 not closed-period

**pay — effects:** SP1 `LOAN_PAYMENT` created · SP2 direction creditor→debtor · SP3 creditor ▼ · SP4 debtor ▲ · SP5 debtor payables ▲ · SP6 creditor receivables ▲ · SP7 other buckets zero · SP8 amount_settled ↑

**repay — validation:** VRp1 amount>0 · VRp2 amount≤remaining · VRp3 capped by disbursed · VRp4 not closed-period

**repay — effects:** SRp1 `LOAN_REPAYMENT` created · SRp2 direction debtor→creditor · SRp3 debtor ▼ · SRp4 creditor ▲ · SRp5 debtor payables ▼ · SRp6 creditor receivables ▼ · SRp7 remaining ▼ · SRp8 multiple accumulate · SRp9 full → fully repayed · SRp10 differential invariant

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no disbursements · VR4 no outstanding repayments · VR5 reason required (view)

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 is reversal · SR4 identity copied · SR5 issuance counter-tx only · SR6 funds flipped · SR7 obligations zero · SR8 differential invariant

**tx reversal / immutability:** TR1 repayment reversed → repaid state restored · TR2 payment reversed · TR3 asymmetric reversal allowed · IM1/IM2/IM3 source/destination/amount immutable

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| Issuance tx | | SC1, SC4 |
| Issuance direction | | SC2 |
| Issuance amount | | SC3 |
| Repay cap pre-disbursement | | SC6, VC12 |
| Aliases | | SC7 |
| Side combinations | | SC8 |
| Active entities | | VC3–VC6 |
| Side type exclusion | | VC1, VC2 |
| Distinctness | | VC15 |
| Amount | | VC7 |
| Officer | | VC8, VC9 |
| Immutability | | IM1–IM3 |
| Balance check flag | | VC12, VP1 |
| Payment tx | | SP1 |
| Payment direction | | SP2 |
| Creditor ▼ | | SP3 |
| Debtor ▲ | | SP4 |
| Multiple disbursements | | VP4 |
| Payables ▲ | | SP5 |
| Receivables ▲ | | SP6 |
| Other buckets zero | | SP7 |
| Repayment tx | | SRp1 |
| Repayment direction | | SRp2 |
| Remaining ▼ | | SRp7 |
| Multiple repayments | | SRp8 |
| Full repayment | | SRp9 |
| Debtor ▼ | | SRp3 |
| Creditor ▲ | | SRp4 |
| Payables ▼ | | SRp5 |
| Receivables ▼ | | SRp6 |
| No-disbursement block | | VRp3, SC6 |
| Disbursed cap | | VRp3 |
| Over-repayment | | VRp2, VRp1 |
| Repay differential | | SRp10, TR1 |
| Repayment reversal restores state | | TR1 |
| Reverse happy path | | SR1–SR4 |
| Counter-tx | | SR5, SR6 |
| Obligations zero | | SR7 |
| Reverse differential | | SR8 |
| Reverse blocked by disbursement | | VR3 |
| Reverse blocked by repayment | | VR4 |
| Reverse constraints | | VR1, VR2 |

---

## 11. Tasks

- [x] Verify issuance transaction created correctly (creditor → debtor, type `LOAN_ISSUANCE`)
- [x] Verify both entities must be `active=True`
- [x] Verify source fund must be `active=True`
- [x] Verify amount/officer validations (zero, negative, non-staff, inactive, no-user)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify repayment view creates transaction in correct direction: `destination.fund → source.fund` (debtor → creditor)
- [x] Verify repayment transaction type is `LOAN_REPAYMENT`
- [x] Verify `amount_remaining_to_repay` property: capped by the disbursed amount
 (`min(issuance_amount, sum(LOAN_PAYMENT)) - sum(repayments)`)
- [x] Verify repayment cannot exceed remaining balance (`amount_remaining_to_repay`)
- [x] Verify repayment is blocked when no disbursement (`LOAN_PAYMENT`) exists
- [x] Verify repayment cannot exceed the total disbursed amount (payment sum)
- [x] Verify creditor fund decreases after payment disbursement
- [x] Verify debtor fund increases after payment disbursement
- [x] Verify multiple payment disbursements allowed
- [x] Verify debtor fund decreases after repayment
- [x] Verify creditor fund increases after repayment
- [x] Verify multiple repayments accumulate correctly
- [x] Verify full repayment marks as fully repayed
- [x] Reversal: only issuance counter-transaction is created (payment disbursements block reversal)
- [x] Verify reversal blocked when payment disbursements exist
- [x] Verify reversal blocked if outstanding repayments exist (debtor → creditor LOAN_REPAYMENT transactions)
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [ ] UI: create form works; detail shows outstanding balance and "Record Repayment" button
- [ ] UI: repayment button shows remaining balance, blocks over-repayment
- [ ] Add a focused test for the payment **balance-insufficient** branch (VP1 failure outcome)
- [ ] Add a focused test for the operation **closed-period** create guard (VC10/VC11) specific to Loan
