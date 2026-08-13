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
| Operation type | `OperationType.CORRECTION_CREDIT` | `OperationType.CORRECTION_DEBIT` | / |
| Proxy class | `CorrectionCreditOperation` | `CorrectionDebitOperation` | / |
| URL slug | `"correction-credit"` | `"correction-debit"` | / |
| Label | `"Correction Credit"` | `"Correction Debit"` | / |
| Theme | `success` / `bi-patch-plus` | `danger` / `bi-patch-minus` | / |
| Source role | `system` | `url` (must be a Project) | / |
| Destination role | `url` (must be a Project) | `system` | / |
| Registered in | `PROXY_MAP` | `PROXY_MAP` | / |
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
| Credit proxy + config + `clean_source`/`clean_destination` | |
| Debit proxy + config + `clean_source`/`clean_destination` | |
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
| Balance exemption (no per-payment gate — `check_balance_on_payment=False`) | `LinkedPaymentTransactionMixin.create_payment_transaction()` skips the gate |
| One-shot guard (single payment, amount == op.amount) | `LinkedPaymentTransactionMixin.create_payment_transaction()` |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | `ReversableModel` + `Operation.reverse()` |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | |
| `CORRECTION_CREDIT_ISSUANCE` / `_PAYMENT` (system → project) | /, /, / |
| `CORRECTION_DEBIT_ISSUANCE` / `_PAYMENT` (project → system) | /, /, / |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Project balance = incoming payment txs − outgoing payment txs | `Entity.balance` → `balance_at` |
| `is_system` / `is_project` role flags (used by `clean_source`/`clean_destination`) | `is_system`, `is_project` |
| Virtual-entity payment exemption (system never balance-checked) | `Entity.can_pay` |
| Open financial period auto-created on entity creation | `Entity.save()` |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (generic, resolves system/url roles) | `OperationCreateView` |
| POST parsing/validation | `OperationDataValidator` |
| Reverse view (reason required) | `operation_reverse_view` |
| Detail view (aggregate amount + reversal action; per-transaction list hidden — one-shot) | `operation_detail_view` |
| URL: `/<pk>/<op_type>/create` | |
| URL: `/<pk>/reverse/` | |
| URL: `/<pk>/detail/` | |
| Templates |. No standard dropdown entry — admin-only routes |

### 2.6 Tests

| Concern | Test file |
|---------|-----------|
| Credit create branches | |
| Credit reverse branches | |
| Debit create branches | |
| Debit reverse branches | |
| Coverage manifest (executable branch registry) | (CC) / (CD) |

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

- **Payment source fund:** `self.source` (system)
- **Payment target fund:** `self.destination` (project)
### Correction Debit (CD)

- **Source (payer):** the **Project** entity in the URL (`is_project=True`). Its fund is the source fund.
- **Destination (receiver):** the **System** entity (`is_system=True`). Virtual — never balance-checked.
- **Transaction flow** (both on create, project → system):

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `CORRECTION_DEBIT_ISSUANCE` | `project.fund → system.fund` | none (issuance, not a payment type) |
| 2 | `CORRECTION_DEBIT_PAYMENT` | `project.fund → system.fund` | ▼ project by `amount` |

- **Payment source fund:** `self.source` (project)
- **Payment target fund:** `self.destination` (system)
---

## 4. Settlement model

Derived from `LinkedPaymentTransactionMixin` using payment-type transactions only:

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
| CC1 | Source is System | `source.is_system` | `ValidationError` | `"Correction Credit source must be the System entity."` | `clean_source` | |
| CC2 | Destination is Project | `destination.is_project` | `ValidationError` | `"Correction Credit destination must be a Project entity."` | `clean_destination` | |
| CC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | `Operation.clean()` | |
| CC4 | Destination entity active | `destination.active` | `ValidationError` | same as CC3 | `Operation.clean()` | |
| CC5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | `SourceFundMixin` | merged with CC3 |
| CC6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | `TargetFundMixin` | merged with CC4 |
| CC7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | |
| CC8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | `OfficerMixin` | |
| CC9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | `OfficerMixin` | |
| CC10 | Date not in a closed period (destination) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | `Operation.clean()` | covered by the shared period suite (see §10) |
| CC11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | `Operation.save()` | covered by the shared period suite (see §10) |
| CC12 | Balance exempt (system payer) | no balance check | never fails | — | `check_balance_on_payment=False` (explicit) + system is virtual | |
| CC13 | Tx entity-type contract | `source.is_system` and `target.is_project` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | `Transaction.create()` | implied by CC1/CC2 (model clean blocks first) |
| CC14 | Tx operation-type allowed | document is `CORRECTION_CREDIT` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | `Transaction.create()` | implied by CC1/CC2 |
| CC15 | No category required | `category_required=False` | never fails | — | `has_category=False` | |

#### 5.1.2 Success effects (CC)

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| CC16 | Issuance tx created | 1 × `CORRECTION_CREDIT_ISSUANCE`, amount `== op.amount`, `system → project` | `LinkedIssuanceTransactionMixin.save()` | |
| CC17 | Payment tx created | 1 × `CORRECTION_CREDIT_PAYMENT`, amount `== op.amount`, `system → project` | `LinkedPaymentTransactionMixin.save()` | same as CC16 |
| CC18 | Tx fund direction | both txs `source=system`, `target=project` | | |
| CC19 | Fully settled immediately | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | `LinkedPaymentTransactionMixin` | |
| CC20 | Project fund ▲ amount | `project.balance` increases by `amount` | `Entity.balance_at` | |
| CC21 | System (virtual) ▼ | system balance moves but is never enforced / never read for checks | `can_pay` virtual exemption | differential invariant |
| CC22 | No invoice / no movements | `has_invoice=False`; no invoice items; no movement lines | `has_invoice=False` | config flag |
| CC23 | Period auto-assigned | `period` = the project's covering period (open period auto-created at entity creation) | `Operation.save()` + `Entity.save()` | covered by shared period suite |

### 5.2 `reverse` — Correction Credit

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches (CC)

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| CC24 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | `ReversableModel._validate_can_be_reversed` + view guard | |
| CC25 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | `ReversableModel._validate_can_be_reversed` + view guard | |
| CC26 | No explicit txs to reverse | all txs are implicit (one-shot issuance + payment) | `ValidationError` (would require manual reversal) | `"You can't reverse this object as it has non-reversed transactions…"` | `ReversableModel._requires_transaction_reversal` + `Operation._implicit_reversable_transaction_types` | implied by successful reverse |
| CC27 | No non-reversed adjustments | n/a — not adjustable | never fails | — | `is_adjustable=False` | n/a |
| CC28 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | `operation_reverse_view` | view contract (see §8) |

#### 5.2.2 Success effects (CC)

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| CC29 | Reversal record created | cloned op, `reversal_of = original` | `ReversableModel.reverse()` | |
| CC30 | Original marked reversed | `original.reversed_by = reversal` | `ReversableModel.reverse()` | |
| CC31 | Reversal inherits identity | `amount`, `source`, `destination` copied | `ReversableModel._get_reverse_kwargs` | |
| CC32 | Counter-tx for issuance | `project → system`, same amount, same type, `reversal_of=original` | `Transaction.reverse()` | |
| CC33 | Counter-tx for payment | `project → system`, same amount, same type, `reversal_of=original` | same as CC32 | |
| CC34 | Counter-txs preserve type | `counter.type == original.type` | same as CC32 | |
| CC35 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | `LinkedIssuanceTransactionMixin.save()` | |
| CC36 | Project fund restored | `project.balance` back to pre-create baseline | `balance_at` | |
| CC37 | Settlement state cleared | `amount_settled == 0`, `is_fully_settled == False` | `amount_settled` | differential invariant; no dedicated focused test yet (see §11) |
| CC38 | Reason flows to reversal | `reversal.description` contains the reason | `ReversableModel.reverse()` | shared engine (see §11 — no dedicated focused test yet) |
| CC39 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger) | whole engine | |

### 5.3 `create` — Correction Debit

Entry points: model `CorrectionDebitOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx, then payment tx).

#### 5.3.1 Validation branches (CD)

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| CD1 | Source is Project | `source.is_project` | `ValidationError` | `"Correction Debit source must be a Project entity."` | `clean_source` | |
| CD2 | Destination is System | `destination.is_system` | `ValidationError` | `"Correction Debit destination must be the System entity."` | `clean_destination` | |
| CD3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | `Operation.clean()` | |
| CD4 | Destination entity active | `destination.active` | `ValidationError` | same as CD3 | `Operation.clean()` | |
| CD5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | `SourceFundMixin` | merged with CD3 |
| CD6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | `TargetFundMixin` | merged with CD4 (system always active) |
| CD7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | |
| CD8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | `OfficerMixin` | |
| CD9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | `OfficerMixin` | |
| CD10 | Date not in a closed period (source) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | `Operation.clean()` | covered by the shared period suite (see §10) |
| CD11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | `Operation.save()` | covered by the shared period suite (see §10) |
| CD12 | Balance exempt (admin tool) | no balance check — debit may drive the fund into deficit | never fails | — | `check_balance_on_payment=False` (explicit) | |
| CD13 | Tx entity-type contract | `source.is_project` and `target.is_system` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | `Transaction.create()` | implied by CD1/CD2 (model clean blocks first) |
| CD14 | Tx operation-type allowed | document is `CORRECTION_DEBIT` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | `Transaction.create()` | implied by CD1/CD2 |
| CD15 | No category required | `category_required=False` | never fails | — | `has_category=False` | |

#### 5.3.2 Success effects (CD)

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| CD16 | Issuance tx created | 1 × `CORRECTION_DEBIT_ISSUANCE`, amount `== op.amount`, `project → system` | `LinkedIssuanceTransactionMixin.save()` | |
| CD17 | Payment tx created | 1 × `CORRECTION_DEBIT_PAYMENT`, amount `== op.amount`, `project → system` | `LinkedPaymentTransactionMixin.save()` | same as CD16 |
| CD18 | Tx fund direction | both txs `source=project`, `target=system` | | |
| CD19 | Fully settled immediately | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | `LinkedPaymentTransactionMixin` | |
| CD20 | Project fund ▼ amount | `project.balance` decreases by `amount` | `Entity.balance_at` | |
| CD21 | System (virtual) ▲ | system balance moves but is never enforced / never read for checks | `can_pay` virtual exemption | differential invariant |
| CD22 | No invoice / no movements | `has_invoice=False`; no invoice items; no movement lines | `has_invoice=False` | config flag |
| CD23 | Period auto-assigned | `period` = the project's covering period (open period auto-created at entity creation) | `Operation.save()` + `Entity.save()` | covered by shared period suite |

### 5.4 `reverse` — Correction Debit

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.4.1 Validation branches (CD)

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| CD24 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | `ReversableModel._validate_can_be_reversed` + view guard | |
| CD25 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | `ReversableModel._validate_can_be_reversed` + view guard | |
| CD26 | No explicit txs to reverse | all txs are implicit (one-shot issuance + payment) | `ValidationError` (would require manual reversal) | `"You can't reverse this object as it has non-reversed transactions…"` | `ReversableModel._requires_transaction_reversal` + `Operation._implicit_reversable_transaction_types` | implied by successful reverse |
| CD27 | No non-reversed adjustments | n/a — not adjustable | never fails | — | `is_adjustable=False` | n/a |
| CD28 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | `operation_reverse_view` | view contract (see §8) |

#### 5.4.2 Success effects (CD)

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| CD29 | Reversal record created | cloned op, `reversal_of = original` | `ReversableModel.reverse()` | |
| CD30 | Original marked reversed | `original.reversed_by = reversal` | `ReversableModel.reverse()` | |
| CD31 | Reversal inherits identity | `amount`, `source`, `destination` copied | `ReversableModel._get_reverse_kwargs` | |
| CD32 | Counter-tx for issuance | `system → project`, same amount, same type, `reversal_of=original` | `Transaction.reverse()` | |
| CD33 | Counter-tx for payment | `system → project`, same amount, same type, `reversal_of=original` | same as CD32 | |
| CD34 | Counter-txs preserve type | `counter.type == original.type` | same as CD32 | |
| CD35 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | `LinkedIssuanceTransactionMixin.save()` | |
| CD36 | Project fund restored | `project.balance` back to pre-create baseline | `balance_at` | |
| CD37 | Settlement state cleared | `amount_settled == 0`, `is_fully_settled == False` | `amount_settled` | differential invariant; no dedicated focused test yet (see §11) |
| CD38 | Reason flows to reversal | `reversal.description` contains the reason | `ReversableModel.reverse()` | shared engine (see §11 — no dedicated focused test yet) |
| CD39 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger) | whole engine | |

### 5.5 `pay` (one-shot guard) — both

There is **no standalone pay action** for either Correction variant:

| Branch | Behavior | Enforced by | Pinned by test |
|--------|----------|-------------|----------------|
| `process_payment()` called | no-op (returns immediately — `can_pay=False`) | `process_payment` | n/a (covered by `can_pay=False`) |
| `create_payment_transaction()` called after create | `ValidationError` — one-shot allows a single payment only, amount must equal `op.amount` | `create_payment_transaction` | |
| `can_pay` flag | `False` on both proxies | class config | |

### 5.6 Immutability — both

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by `ImmutableMixin` via `_immutable_fields`.

| Branch | Enforced by | Credit pinned by | Debit pinned by |
|--------|-------------|------------------|-----------------|
| `source` changed after save | `ImmutableMixin.save()` | | |
| `destination` changed after save | `ImmutableMixin.save()` | | |
| `amount` changed after save | `ImmutableMixin.save()` | | |

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — `Entity.save()`.
- The operation's governing entity (`period_entity`) is the **project** (Credit: `_dest_role = "url"`; Debit: `_source_role = "url"`) — `Operation.period_entity`.
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (CC11/CD11).
- New operations dated inside a **closed** period are rejected (CC10/CD10) — `is_date_in_closed_period`.
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period (`_reverse_period`).

---

## 7. Entity roles & balance contract

- **Credit:** system is the only allowed source; project the only allowed destination — enforced at model (CC1/CC2) and transaction (CC13) layers.
- **Debit:** project is the only allowed source; system the only allowed destination — enforced at model (CD1/CD2) and transaction (CD13) layers.
- `project.balance` is derived exclusively from **payment-type** transactions (`balance_at`); the issuance tx never moves a balance.
- System is **virtual**: `can_pay` always returns `True`, so neither variant is ever blocked by fund balance (CC12/CD12). In particular, a **Correction Debit may drive the project fund into deficit** — this is intentional (admin tool for fixing ledger errors) and pinned by.
- Corrections carry **no category** and **no invoice/movements** — they touch only balances (CC15/CD15).

---

## 8. View / UI contract

| Concern | Correction Credit | Correction Debit |
|---------|-------------------|------------------|
| Create route | `POST/GET /<project_pk>/correction-credit/create` → `OperationCreateView` | `POST/GET /<project_pk>/correction-debit/create` → `OperationCreateView` |
| Source selection | locked to the **System** entity (`_source_role="system"`, resolved by `resolve_request`); no picker | the **Project** from the URL (`_source_role="url"`); no picker |
| Destination selection | the **Project** from the URL (`_dest_role="url"`); no secondary-entity field | locked to the **System** entity (`_dest_role="system"`); no picker |
| Category | hidden (no category) | hidden (no category) |
| Amount | raw `amount` POST field (`_compute_amount`); validated > 0 at model; never balance-gated | raw `amount` POST field (`_compute_amount`); validated > 0 at model; never balance-gated |
| POST parsing | `OperationDataValidator` — date format, description, category (n/a), `amount_paid` (n/a, forced 0) | same |
| List entry | **no standard dropdown entry** — admin-only routes | same |
| Detail | `operation_detail_view` — shows the operation total + settlement status + reversal action; the individual issuance/payment transactions are hidden (one-shot — two identical amounts would confuse users) | same |
| Reverse | `operation_reverse_view` — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (CC24/CC25) | `operation_reverse_view` — same guards (CD24/CD25) |

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
| CC Tx creation + counts | | CC16, CC17 |
| CC Tx direction | | CC18 |
| CC Settlement | | CC19 |
| CC Project ▲ | | CC20 |
| CC No category | | CC15 |
| CC Source/dest validation | | CC1, CC2 |
| CC Active entities | | CC3–CC6 |
| CC Amount/officer | | CC7–CC9 |
| CC Immutability | | IM1–IM3 |
| CC One-shot / balance | | BP1, BP2, CC12 |
| CC Reverse happy path | | CC29–CC31 |
| CC Counter txs | | CC32–CC35 |
| CC Project restored | | CC36 |
| CC Differential invariant | | CC39, CC37, CC21 |
| CC Reverse constraints | | CC24, CC25 |
| CD Tx creation + counts | | CD16, CD17 |
| CD Tx direction | | CD18 |
| CD Settlement | | CD19 |
| CD Project ▼ | | CD20 |
| CD No category | | CD15 |
| CD Source/dest validation | | CD1, CD2 |
| CD Active entities | | CD3–CD6 |
| CD Amount/officer | | CD7–CD9 |
| CD Immutability | | IM1–IM3 |
| CD Balance exempt | | CD12 |
| CD One-shot / can_pay | | BP1, BP2 |
| CD Reverse happy path | | CD29–CD31 |
| CD Counter txs | | CD32–CD35 |
| CD Project restored | | CD36 |
| CD Differential invariant | | CD39, CD37, CD21 |
| CD Reverse constraints | | CD24, CD25 |

