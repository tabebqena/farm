# Birth — Operation Contract

**Epic:** Inventory / Livestock — One-Shot
**Type:** One-shot, auto-settled, creates assets (`creates_assets=True`, `has_invoice=True`)
**Actions:** `create`, `move items` (auto), `reverse`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Birth** operation.
> Every clause below is registered to its implementing code (model → mixin → transaction → view) and to its pinning test.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> See [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md) for the shared structure and
> [`op_1_cash_injection.md`](op_1_cash_injection.md) for a fully worked example.

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.BIRTH` (`"BIRTH"`) | |
| Proxy class | `BirthOperation` | |
| URL slug | `"birth"` | |
| Label | `"Birth"` | |
| Theme | `danger` / `bi-box-arrow-up-right` (inherited default) | |
| Source role | `system` | |
| Destination role | `url` (must be a Project) | |
| Registered in | `PROXY_MAP` | |
| Cross-op reference | row BI | [`operations-comparison.md`](operations-comparison.md) |

**Configuration flags**:

| Flag | Value | Meaning |
|------|-------|---------|
| `_issuance_transaction_type` | `BIRTH_ISSUANCE` | issuance tx created on save |
| `_payment_transaction_type` | `BIRTH_PAYMENT` | payment tx created on save (one-shot) — **non-cash bookkeeping** |
| `_is_one_shot_operation` | `True` | payment fires at create; no standalone pay action |
| `can_pay` | `False` | `process_payment()` is a no-op |
| `is_partially_payable` | `False` | payment must equal amount (one-shot) |
| `max_payment_transaction_count` | `1` | exactly one payment tx ever |
| `check_balance_on_payment` | `False` | system payer — no fund-balance check at create |
| `has_category` / `category_required` | `False` | no financial category |
| `has_repayment` | `False` | no repayment action |
| `has_invoice` | `True` | invoice items + auto inventory movements |
| `creates_assets` / `can_create_movement` | `True` | new assets are created (lazy products), auto inbound movements |

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row links the clause to the code that must honor it.

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_source`/`clean_destination` + payment funds | |
| Proxy registry / URL→class resolution | |
| Shared `Operation` engine (`clean`, `save`, `reverse`, `create`, `resolve_request`, `save_inventory`, `_auto_create_inventory_movements`, period assignment, reversable tx types) | |
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
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | `ReversableModel` + `Operation.reverse()` |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | |
| `BIRTH_ISSUANCE` (system → project, no balance) | |
| `BIRTH_PAYMENT` (system → project, **non-cash — excluded from `payment_types()`**) | |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Balance derivation (payment types only — `BIRTH_PAYMENT` excluded, so a birth never moves a fund balance) | `Entity.balance_at` |
| Virtual/system-entity payment exemption | `Entity.can_pay` |
| Open financial period auto-created on entity creation | `Entity.save()` |

### 2.5 Inventory layer (birth-specific)

| Concern | Implementing code |
|---------|-------------------|
| Giving-birth template gating: ANIMAL nature only; `gives_birth_to` FK; FEMALE/MIXED gender; `clean()` enforcement | `gives_birth_to`, `clean`, `accepts_operation` |
| Newborn template defaults to mother's `gives_birth_to`; mother picker restricted to ACTIVE female/mixed project animals | (birth fields, default newborn ) |
| Lazy product creation per head (gender / birth_date / mother forwarded via transient attrs) | (`_auto_create_inventory_movements`) |
| Auto inbound movement lines + `Product` creation, status ACTIVE | (`Product.status` ) |
| Identity: `INDIVIDUAL` tracking requires a unique tag per entity | `Product.Meta` (`UniqueConstraint(entity, unique_id)`), `next_tag` |
| Movement-based valuation (`movement_state`, `inventory_value`) — born value carried **once** in inventory | `inventory_value`, `_INBOUND_TYPES` |

### 2.6 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (dedicated Birth) | `BirthCreateView` |
| POST parsing/validation | `OperationDataValidator` |
| Reverse view (reason required) | `operation_reverse_view` |
| Detail view (aggregate amount + movement lines + reversal action; per-transaction list hidden — one-shot) | `operation_detail_view` |
| URL: `/<pk>/birth/create` | |
| URL: `/<pk>/reverse/` | |
| URL: `/<pk>/detail/` | |
| Templates | |

### 2.7 Tests

| Concern | Test file |
|---------|-----------|
| Create branches (validation, issuance + payment, auto inbound movement, lazy product creation, ACTIVE status, ledger) | |
| Reverse branches (reversal record, counter-tx, auto lines reversed, negated ledger, born products REMOVED) | |
| Newborn animal attributes (mother / gender / birth_date / `gives_birth_to` default) | |
| Coverage manifest (executable branch registry) | |

---

## 3. Money flow & entities

- **Source (payer):** the single **System** entity (`is_system=True`). Virtual — never balance-checked, exempt from fund-balance validation (`payment_source_fund`).
- **Destination (receiver):** the **Project** entity in the URL (`is_project=True`). Its fund is the target fund; the newborn assets belong to this project.
- **Transaction flow** (both on create, system → project):

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `BIRTH_ISSUANCE` | `system.fund → project.fund` | none (issuance, not a payment type) |
| 2 | `BIRTH_PAYMENT` | `system.fund → project.fund` | **none** — non-cash bookkeeping, **excluded from `payment_types()`** |

- **Payment source fund:** `self.source` (system)
- **Payment target fund:** `self.destination` (project)
> **No cash flow.** The born animal's value is carried **exactly once**, in movement-based inventory value (`inventory_value()`). It **never** appears in the project's fund balance (`BIRTH_PAYMENT` is non-cash — not in `payment_types()`, so no balance/payable/receivable effect) and is **not** recognized in `profit_loss` at birth (capitalized as an asset, not income).

---

## 4. Settlement model

Derived from `LinkedPaymentTransactionMixin` using payment-type transactions only (note: `BIRTH_PAYMENT` is **not** a payment type for balance purposes, but it *is* the one-shot settlement transaction for this operation):

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

Entry points: model `BirthOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx, then payment tx), then the invoice formset → `save_inventory()` → `_auto_create_inventory_movements()`.

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source is System | `source.is_system` | `ValidationError` | `"Birth source must be the System entity."` | `clean_source` | |
| VC2 | Destination is Project | `destination.is_project` | `ValidationError` | `"Birth destination must be a Project entity."` | `clean_destination` | |
| VC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | `Operation.clean()` | shared engine suite (cf. [`op_1`](op_1_cash_injection.md) VC3) |
| VC4 | Destination entity active | `destination.active` | `ValidationError` | same as VC3 | `Operation.clean()` | shared engine suite |
| VC5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | `SourceFundMixin` | shared engine suite |
| VC6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | `TargetFundMixin` | shared engine suite |
| VC7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | |
| VC8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | `OfficerMixin` | |
| VC9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | `OfficerMixin` | |
| VC10 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | `Operation.clean()` | period suite |
| VC11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | `Operation.save()` | period suite |
| VC12 | Balance exempt (system payer) | no balance check | never fails | — | `check_balance_on_payment=False` | |
| VC13 | Tx entity-type contract | `source.is_system` and `target.is_project` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | `Transaction.create()` | implied by VC1/VC2 (model clean blocks first) |
| VC14 | Tx operation-type allowed | document is `BIRTH` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | `Transaction.create()` | implied by VC1/VC2 |
| VC15 | Source ≠ target | system ≠ project | always true | `"Source and target funds must be different."` | `Transaction.clean()` | structural (system ≠ project) |
| VC16 | Template is a giving-birth (or newborn) ANIMAL | template `nature == ANIMAL` (BIRTH allowed) | `ValidationError` | template rejected by `accepts_operation(BIRTH)` | `ProductTemplate.accepts_operation` | (nature gating) |
| VC17 | Mother is an ACTIVE female/mixed animal of the project (when a mother is picked) | mother in restricted queryset | form `ValidationError` | mother picker restricted | `InvoiceItemCreateForm` | |
| VC18 | Newborn template present | `product_template` chosen (defaults to mother's `gives_birth_to`) | form `ValidationError` | `"Newborn template is required (or select a mother whose template has a 'gives birth to' template)."` | `InvoiceItemCreateForm.clean()` | |
| VC19 | Identity — unique tag per entity | `INDIVIDUAL` tracking: `unique_id` present + unique per `(entity, unique_id)` | `ValidationError` / `IntegrityError` | DB `UniqueConstraint` | `Product.Meta` | |
| VC20 | Unit consistency | quantity is a multiple of `product_template.minimum_quantity` | `ValidationError` | unit-step error | inventory form / movement clean | shared inventory suite |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | 1 × `BIRTH_ISSUANCE`, amount `== op.amount`, `system → project` | `LinkedIssuanceTransactionMixin.save()` | |
| SC2 | Payment tx created (non-cash) | 1 × `BIRTH_PAYMENT`, amount `== op.amount`, `system → project`; **not** a `payment_types()` type → no balance/payable/receivable effect | `LinkedPaymentTransactionMixin.save()` | same as SC1 |
| SC3 | Tx amounts equal op amount | both txs `amount == op.amount` | transaction creation | |
| SC4 | Tx fund direction | both txs `source=system`, `target=project` | | |
| SC5 | Fully settled immediately | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | `LinkedPaymentTransactionMixin` | |
| SC6 | No cash flow | project fund balance unchanged (payment non-cash); system (virtual) ▼ in bookkeeping only | `payment_types()` exclusion + `Entity.balance_at` | differential invariant (cf. pattern) |
| SC7 | Auto inbound movement lines | `INDIVIDUAL` → one line per head (qty 1, shared `group_key`); `COMMODITY` → one line at item qty | `_auto_create_inventory_movements` | |
| SC8 | Lazy product creation | each head lazy-creates its own tagged `Product` (qty 1, unique tag) | + `Product` lazy-create | |
| SC9 | Newborn status ACTIVE | each created product `status == ACTIVE` | `Product.status` | |
| SC10 | Newborn attributes recorded | `gender`, `birth_date`, `mother` set on the newborn | birth flow `birth_attrs` | |
| SC11 | Newborn template defaulted | newborn `product_template == mother.gives_birth_to` unless overridden | `InvoiceItemCreateForm.clean()` | |
| SC12 | Inventory value increases once | `movement_state(product)` → `qty > 0`, `value = qty × carried cost`; `inventory_value()` includes the born value; `FinancialPeriod.end_assets` ▲ once (via inventory, not cash) | `movement_state` + `inventory_value` | |
| SC13 | Period auto-assigned | `period` = the project's covering period (open period auto-created at entity creation) | `Operation.save()` + `Entity.save()` | covered by period suite |

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | `ReversableModel._validate_can_be_reversed` + view guard | |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | `ReversableModel._validate_can_be_reversed` + view guard | |
| VR3 | No explicit txs to reverse | all txs are implicit (one-shot issuance + payment) | `ValidationError` (would require manual reversal) | `"You can't reverse this object as it has non-reversed transactions…"` | `ReversableModel._requires_transaction_reversal` + `Operation._implicit_reversable_transaction_types` | implied by successful reverse |
| VR4 | No non-reversed adjustments | n/a — Birth is not adjustable | never fails | — | `is_adjustable=False` | n/a |
| VR5 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | `operation_reverse_view` | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | `ReversableModel.reverse()` | |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | `ReversableModel.reverse()` | |
| SR3 | Reversal inherits identity | `amount`, `source`, `destination` copied | `ReversableModel._get_reverse_kwargs` | structural (same engine as [`op_1`](op_1_cash_injection.md) SR3) |
| SR4 | Counter-tx for issuance | `project → system`, same amount, same type, `reversal_of=original` | `Transaction.reverse()` | |
| SR5 | Counter-tx for payment | `project → system`, same amount, same type, `reversal_of=original` | same as SR4 | same as SR4 |
| SR6 | Counter-txs preserve type + amount | `counter.type == original.type`, `counter.amount == original.amount` | same as SR4 | same as SR4 |
| SR7 | Auto movement lines reversed | one reversal line per original (equal qty, `reversal_of` link); originals preserved | `Operation.reverse()` → `line.reverse()` | |
| SR8 | Ledger negated | each born product's net presence → `qty 0`, `value 0` | `movement_state` | |
| SR9 | Born products removed from stock | products persist (audit trail) but `status == REMOVED`; `validate_active()` fails → barred from new operations; value leaves `inventory_value()` | `Product.status` + `validate_active` | |
| SR10 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | `LinkedIssuanceTransactionMixin.save()` | shared engine (cf. [`op_1`](op_1_cash_injection.md) SR7) |
| SR11 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger, inventory value) | whole engine | shared engine invariant |

### 5.3 `pay` (one-shot guard)

There is **no standalone pay action** for Birth:

| Branch | Behavior | Enforced by | Pinned by test |
|--------|----------|-------------|----------------|
| `process_payment()` called | no-op (returns immediately — `can_pay=False`) | `process_payment` | n/a (covered by `can_pay=False`) |
| `create_payment_transaction()` called after create | `ValidationError` — one-shot allows a single payment only, amount must equal `op.amount` | `create_payment_transaction` | |

### 5.4 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by `ImmutableMixin` via `_immutable_fields`. Shared with every operation (see [`op_1`](op_1_cash_injection.md) §5.4).

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — `Entity.save()`.
- The operation's governing entity (`period_entity`) is the **destination project** (`_dest_role = "url"`) — `Operation.period_entity`. The System (virtual) has no periods and is exempt.
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC11).
- New operations dated inside a **closed** period are rejected (VC10).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period (`_reverse_period`).

---

## 7. Entity roles & balance contract

- System is the only allowed source; Project the only allowed destination — enforced at model (VC1/VC2) and transaction (VC13) layers.
- `BIRTH_PAYMENT` is **deliberately excluded** from `payment_types()` — it is a non-cash bookkeeping record. The project's fund balance, payables and receivables are **never** affected by a birth.
- The born asset's value is carried **exactly once** in movement-based inventory value (`inventory_value()`); `FinancialPeriod.end_assets` = cash + movement-based inventory + loans + advances, so a birth increases `end_assets` exactly once, via inventory.
- System is **virtual**: `can_pay` always returns `True`, so births are never blocked by fund balance (VC12).

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Create route | `POST/GET /<project_pk>/birth/create` → `BirthCreateView` |
| Source selection | locked to the single **System** entity (`_source_role="system"`); no picker |
| Destination selection | the **Project** from the URL (`_dest_role="url"`); `get_related_entities` returns `[]` → no secondary-entity field |
| Category | hidden (no category) |
| Amount | computed from item totals; raw `amount` POST field validated > 0 at model |
| Invoice items | `InvoiceItemCreateFormSet` with `is_birth=True` — newborn `product_template`, `quantity`, `unit_price`, plus birth-only fields `mother`, `gender`, `birth_date` |
| Giving-birth product | the **mother** picker lists only **ACTIVE FEMALE/MIXED** animals owned by the project (template `gender`/`gives_birth_to`); a template "can give birth" when `nature=ANIMAL`, `gender ∈ {FEMALE, MIXED}` and `gives_birth_to` is set (`ProductTemplate.clean`) |
| Born product type | the newborn `product_template` defaults to the mother's `gives_birth_to` (e.g. Dairy Cow → Calf); the user may override with any ANIMAL template selectable for the project |
| POST parsing | `OperationDataValidator` — date format, description, category (n/a), `amount_paid` (n/a, forced 0) |
| List entry | "Birth" link |
| Detail | `operation_detail_view` — shows the operation total + settlement status + auto movement lines + reversal action; the individual issuance/payment transactions are hidden (one-shot — two identical amounts would confuse users) |
| Reverse | `operation_reverse_view` — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source=system · VC2 dest=project · VC3 source active · VC4 dest active · VC5 source fund active · VC6 target fund active · VC7 amount>0 · VC8 officer staff · VC9 officer active · VC10 not closed-period · VC11 covering period exists · VC12 balance exempt · VC13 tx entity-type · VC14 tx op-type · VC15 source≠target · VC16 template is ANIMAL (giving-birth/newborn) · VC17 mother active female/mixed · VC18 newborn template present · VC19 unique tag per entity · VC20 unit multiple

**create — effects:** SC1 issuance tx · SC2 non-cash payment tx · SC3 amounts equal · SC4 direction system→project · SC5 settled immediately · SC6 no cash flow · SC7 auto inbound lines · SC8 lazy product creation · SC9 status ACTIVE · SC10 newborn attributes · SC11 newborn template defaulted · SC12 inventory value ▲ once · SC13 period assigned

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no explicit txs · VR4 no adjustments (n/a) · VR5 reason required (view)

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 identity copied · SR4 issuance counter-tx · SR5 payment counter-tx · SR6 type/amount preserved · SR7 auto lines reversed · SR8 ledger negated · SR9 born products REMOVED · SR10 reversal owns no txs · SR11 differential invariant

**pay / immutability:** BP1 `process_payment` no-op · BP2 `create_payment_transaction` blocked after create · IM1/IM2/IM3 source/destination/amount immutable

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| Config flags | | flags |
| Tx creation + counts | | SC1, SC2 |
| Tx direction | | SC4 |
| Tx amounts | | SC3 |
| Settlement | | SC5 |
| Source validation | | VC1 |
| Destination validation | | VC2 |
| Amount | | VC7 |
| Officer | | VC8, VC9 |
| Auto inbound lines | | SC7 |
| Lazy tagged products | | SC8, VC19 |
| ACTIVE status | | SC9 |
| Ledger / movement state | | SC12 |
| One-shot guard | | BP2 |
| Newborn attributes | | SC10 |
| Newborn template default | | SC11, VC18 |
| Reverse happy path | | SR1, SR2 |
| Counter txs | | SR4–SR6 |
| Auto lines reversed | | SR7, SR8 |
| Born products removed | | SR9 |
| Reverse constraints | | VR1, VR2 |
| Reversed-birth stock removal | | SR9 |
