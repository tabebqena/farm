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
| Operation type | `OperationType.INTERNAL_TRANSFER` (`"INTERNAL_TRANSFER"`) | |
| Proxy class | `InternalTransferOperation` | |
| URL slug | `"internal-transfer"` | |
| Label | `"Internal Transfer"` | |
| Theme | `danger` / `bi-box-arrow-up-right` (inherited default — not overridden) | |
| Source role | `url` (must be an internal Person) | |
| Destination role | `post` (must be an internal Person, picked from secondary field) | |
| Registered in | `PROXY_MAP` | |
| Cross-op reference | row IT | [`operations-comparison.md`](operations-comparison.md) |

**Configuration flags**:

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
| Proxy class + type-specific config + `clean()` (internal/source/dest/system-world guards + balance) | |
| Destination picker (`get_related_entities` — all Persons except the URL person) | |
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
| `INTERNAL_TRANSFER_ISSUANCE` (non-virtual → non-virtual) | |
| `INTERNAL_TRANSFER_PAYMENT` (non-virtual → non-virtual, affects balance) | |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Person balance = incoming payment txs − outgoing payment txs | `Entity.balance` → `balance_at` |
| `is_internal` flag (both sides must be internal — VC1/VC2) | `Entity.is_internal` |
| `is_virtual` flag (system/world excluded — VC3/VC4) | `Entity.is_virtual` |
| Balance enforcement: `can_pay` only balance-checks real (non-virtual) internal funds | `Entity.can_pay` |
| Open financial period auto-created on entity creation | `Entity.save()` |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (generic, resolves URL person source + `post` person destination) | `OperationCreateView` |
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

- **Source (payer):** the **internal Person** entity in the URL (`is_internal=True`). Its fund is the source fund and is **balance-checked at create** (VC12).
- **Destination (receiver):** an **internal Person** entity picked via the secondary field (`is_internal=True`). System and World are excluded on both sides (VC3/VC4).
- **Transaction flow** (both on create, source → destination):

> **Requirement — no virtual funds.** Neither the source nor the destination of an Internal Transfer may be a **virtual** entity (**System** or **World**) — virtual funds have no transferable internal balance, so transfers are strictly between **real internal funds**. Enforced at the model (VC3/VC4) and again at the transaction layer (VC15 — requires `not_virtual` on both sides).

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `INTERNAL_TRANSFER_ISSUANCE` | `source.fund → destination.fund` | none (issuance, not a payment type) |
| 2 | `INTERNAL_TRANSFER_PAYMENT` | `source.fund → destination.fund` | ▼ source by `amount`; ▲ destination by `amount` |

- **Payment source fund:** `self.source` (internal person)
- **Payment target fund:** `self.destination` (internal person)
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

Entry points: model `InternalTransferOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx, then payment tx).

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source is internal | `source.is_internal` | `ValidationError` | `"Internal Transfer source must be an internal entity."` | `clean()` | |
| VC2 | Destination is internal | `destination.is_internal` | `ValidationError` | `"Internal Transfer destination must be an internal entity."` | `clean()` | |
| VC3 | Source not system/world | `not (source.is_system or source.is_world)` | `ValidationError` | `"Internal Transfer source cannot be a system or world entity."` | `clean()` | |
| VC4 | Destination not system/world | `not (destination.is_system or destination.is_world)` | `ValidationError` | `"Internal Transfer destination cannot be a system or world entity."` | `clean()` | |
| VC5 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | `Operation.clean()` | |
| VC6 | Destination entity active | `destination.active` | `ValidationError` | same as VC5 | `Operation.clean()` | |
| VC7 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | `SourceFundMixin` | merged with VC5 |
| VC8 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | `TargetFundMixin` | merged with VC6 |
| VC9 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | |
| VC10 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | `OfficerMixin` | |
| VC11 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | `OfficerMixin` | |
| VC12 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | `Operation.clean()` | covered by the shared period suite (see §10) |
| VC13 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | `Operation.save()` | covered by the shared period suite (see §10) |
| VC14 | Balance checked at create (source pays) | `payment_source_fund.can_pay(amount)` | `ValidationError` | `"Insufficient funds: source fund balance (%(balance)s) is less than transfer amount (%(amount)s)."` | `Entity.can_pay` | |
| VC15 | Tx entity-type contract | `source.is_virtual == False` and `target.is_virtual == False` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | `Transaction.create()` | implied by VC1–VC4 (model clean blocks first) |
| VC16 | Tx operation-type allowed | document is `INTERNAL_TRANSFER` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | `Transaction.create()` | implied by VC1–VC4 |
| VC17 | Source ≠ destination | distinct internal persons | `ValidationError` | `"Source and target funds must be different."` | `Transaction.clean()` + picker excludes URL person | structural (picker excludes the URL person) |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | 1 × `INTERNAL_TRANSFER_ISSUANCE`, amount `== op.amount`, `source → destination` | `LinkedIssuanceTransactionMixin.save()` | |
| SC2 | Payment tx created | 1 × `INTERNAL_TRANSFER_PAYMENT`, amount `== op.amount`, `source → destination` | `LinkedPaymentTransactionMixin.save()` | same as SC1 |
| SC3 | Tx amounts equal op amount | both txs `amount == op.amount` | transaction creation | shared engine (see §11 — no dedicated focused test yet) |
| SC4 | Tx fund direction | both txs `source=source`, `target=destination` | | |
| SC5 | Fully settled immediately | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | `LinkedPaymentTransactionMixin` | |
| SC6 | Source fund ▼ amount | `source.balance` decreases by `amount` | `Entity.balance_at` | |
| SC7 | Destination fund ▲ amount | `destination.balance` increases by `amount` | `Entity.balance_at` | |
| SC8 | No invoice / no movements | `has_invoice=False`; no invoice items; no movement lines | `has_invoice=False` | config flag (`has_invoice=False`); no ledger/movement machinery in `post_save_tasks` |
| SC9 | Period auto-assigned | `period` = the source's covering period (open period auto-created at entity creation) | `Operation.save()` + `Entity.save()` | covered by shared period suite |

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | `ReversableModel._validate_can_be_reversed` + view guard | |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | `ReversableModel._validate_can_be_reversed` + view guard | |
| VR3 | No explicit txs to reverse | all txs are implicit (one-shot issuance + payment) | `ValidationError` (would require manual reversal) | `"You can't reverse this object as it has non-reversed transactions…"` | `ReversableModel._requires_transaction_reversal` + `Operation._implicit_reversable_transaction_types` | implied by successful reverse |
| VR4 | No non-reversed adjustments | n/a — Internal Transfer is not adjustable | never fails | — | `is_adjustable=False` | n/a |
| VR5 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | `operation_reverse_view` | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | `ReversableModel.reverse()` | |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | `ReversableModel.reverse()` | |
| SR3 | Reversal inherits identity | `amount`, `source`, `destination` copied | `ReversableModel._get_reverse_kwargs` | |
| SR4 | Counter-tx for issuance | `destination → source`, same amount, same type, `reversal_of=original` | `Transaction.reverse()` | |
| SR5 | Counter-tx for payment | `destination → source`, same amount, same type, `reversal_of=original` | same as SR4 | |
| SR6 | Counter-txs preserve type + amount | `counter.type == original.type`, `counter.amount == original.amount` | same as SR4 | |
| SR7 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | `LinkedIssuanceTransactionMixin.save()` | |
| SR8 | Source + destination restored | both balances back to pre-create baseline | `balance_at` | |
| SR9 | Settlement state cleared | `amount_settled == 0`, `is_fully_settled == False` | `amount_settled` | differential invariant; no dedicated focused test yet (see §11) |
| SR10 | Reason flows to reversal | `reversal.description` contains the reason | `ReversableModel.reverse()` | shared engine (see §11 — no dedicated focused test yet) |
| SR11 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger) | whole engine | |

### 5.3 `pay` (one-shot guard)

There is **no standalone pay action** for Internal Transfer:

| Branch | Behavior | Enforced by | Pinned by test |
|--------|----------|-------------|----------------|
| `process_payment()` called | no-op (returns immediately — `can_pay=False`) | `process_payment` | n/a (covered by `can_pay=False`) |
| `create_payment_transaction()` called after create | `ValidationError` — one-shot allows a single payment only, amount must equal `op.amount` (balance re-checked first, VC14) | `create_payment_transaction` | |

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
- The operation's governing entity (`period_entity`) is the **source person** (`_source_role = "url"`) — `Operation.period_entity`.
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC13).
- New operations dated inside a **closed** period are rejected (VC12) — `is_date_in_closed_period`.
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period (`_reverse_period`).

---

## 7. Entity roles & balance contract

- **Requirement — no virtual funds.** A virtual entity (**System** or **World**) can never be the source or the destination of an Internal Transfer, because a virtual fund cannot own a transferable balance. Enforced at model `clean()` (VC3/VC4 — `"Internal Transfer source/destination cannot be a system or world entity."`) and again at the transaction layer (VC15 — requires `not_virtual` on both sides, ).
- Both sides must additionally be **internal** (VC1/VC2) — enforced at model `clean()`.
- `source.balance` / `destination.balance` are derived exclusively from **payment-type** transactions (`balance_at`); the issuance tx never moves a balance.
- The source fund is a **real internal fund** and is balance-checked at create (`clean()`, VC14). `check_balance_on_payment` stays `False` — the balance is guaranteed once at creation, and the one-shot payment then matches it exactly.
- Source ≠ destination is guaranteed structurally by the picker (which excludes the URL person) plus the `Transaction.clean()` guard (VC17).

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Create route | `POST/GET /<person_pk>/internal-transfer/create` → `OperationCreateView` |
| Source selection | the **internal Person** from the URL (`_source_role="url"`, resolved by `resolve_request`); no picker |
| Destination selection | an **internal Person** picked from the secondary field (`_dest_role="post"`); `get_related_entities` returns all Person entities except the URL person (internal-ness enforced at model `clean()`) |
| Category | hidden (no category) |
| Amount | raw `amount` POST field (`_compute_amount`); validated > 0 at model; balance-checked at create (VC14) |
| POST parsing | `OperationDataValidator` — date format, description, category (n/a), `amount_paid` (n/a, forced 0) |
| List entry | "Internal Transfer" link |
| Detail | `operation_detail_view` — shows the operation total + settlement status + reversal action; the individual issuance/payment transactions are hidden (one-shot — two identical amounts would confuse users) |
| Reverse | `operation_reverse_view` — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

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
| Tx creation + counts | | SC1, SC2 |
| Tx direction | | SC4 |
| Settlement | | SC5 |
| Source internal | | VC1, VC3 |
| Destination internal | | VC2, VC4 |
| Active entities | | VC5–VC8 |
| Balance check | | VC14 |
| Amount | | VC9 |
| Officer | | VC10, VC11 |
| Immutability | | IM1–IM3 |
| One-shot guard | | BP2 |
| Source ▼ / destination ▲ | | SC6, SC7 |
| Reverse happy path | | SR1–SR3 |
| Counter txs | | SR4–SR7 |
| Reverse constraints | | VR1, VR2 |
| Balance restored | | SR8 |
| Differential invariant | | SR11, SR9 |

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
- [x] UI: operation detail shows the aggregate amount + reversal action; per-transaction list hidden for one-shot
- [ ] Add a dedicated focused for Internal Transfer (SC3 currently pinned only by the shared engine)
- [ ] Add a dedicated focused for Internal Transfer (SR9 currently pinned only by the differential invariant)
- [ ] Add a dedicated focused for Internal Transfer (SR10 currently pinned only by the shared engine)
