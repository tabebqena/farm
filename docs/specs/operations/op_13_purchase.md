# Purchase — Operation Contract

**Epic:** 11.1 — Payable Operations
**Type:** Multi-stage — non-one-shot, partially payable, invoice-based (payable + inventory)
**Actions:** `create`, `pay`, `move items`, `adjust items`, `adjust`, `reverse`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Purchase** operation.
> Every clause below is registered to its implementing code (model → mixin → transaction → view) and to its pinning test.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> See [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md) for the shared structure and
> [`op_1_cash_injection.md`](op_1_cash_injection.md) for a fully worked example.

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.PURCHASE` (`"PURCHASE"`) | |
| Proxy class | `PurchaseOperation` | |
| URL slug | `"purchase"` | |
| Label | `"Purchase Issuance"` | |
| Theme | n/a — not defined on proxy (defaults) | |
| Source role | `url` (a Project entity) | |
| Destination role | `post` (a Vendor entity, selected) | |
| Registered in | `PROXY_MAP` | |
| Cross-op reference | row PU | [`operations-comparison.md`](operations-comparison.md) |

**Configuration flags**:

| Flag | Value | Meaning |
|------|-------|---------|
| `_issuance_transaction_type` | `PURCHASE_ISSUANCE` | obligation tx created on save (non-cash) |
| `_payment_transaction_type` | `PURCHASE_PAYMENT` | cash tx created per payment |
| `_is_one_shot_operation` | `False` | no payment fires at create; standalone `pay` action |
| `can_pay` | `True` | `process_payment()` is active |
| `is_partially_payable` | `True` | payments can be any fraction of the amount |
| `max_payment_transaction_count` | `-1` | unlimited partial payments |
| `check_balance_on_payment` | `True` | each payment is balance-checked against the project fund |
| `has_category` / `category_required` | `False` | no financial category |
| `has_repayment` | `False` | no repayment action |
| `has_invoice` | `True` | invoice items + inventory movements |
| `creates_assets` | `True` | received goods enter project inventory |
| `is_adjustable` / `is_items_adjustable` | `True` / `True` | amount + invoice-item adjustments allowed |
| `category_type` | `"PURCHASE"` | category namespace (unused while `has_category=False`) |

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row links the clause to the code that must honor it.

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_source`/`clean_destination` + `create_from_session` | |
| Proxy registry / URL→class resolution | |
| Shared `Operation` engine (`clean`, `save`, `reverse`, `process_payment`, period assignment, reversable tx types) | |
| Operation type enum | |

### 2.2 Core engine (mixins / base)

| Concern | Implementing code |
|---------|-------------------|
| Immutability of `source`/`destination`/`amount`/`period` | `ImmutableMixin` + `_immutable_fields` |
| Amount must be > 0 | `AmountCleanMixin` |
| Officer must be staff + active | `OfficerMixin` |
| Source fund exists + active | `SourceFundMixin` |
| Target fund exists + active | `TargetFundMixin` |
| Issuance tx creation on save (skipped for reversals) | `LinkedIssuanceTransactionMixin` |
| Payment / settlement (`amount_settled`, `remaining`, `is_fully_settled`, balance check, over-payment guard) | `LinkedPaymentTransactionMixin` |
| Repayment | n/a — `has_repayment=False` |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | `ReversableModel` + `Operation.reverse()` |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | |
| `PURCHASE_ISSUANCE` (project → vendor, non-cash) | |
| `PURCHASE_PAYMENT` (project → vendor, affects balance) | |
| `PURCHASE_ADJUSTMENT_INCREASE` (project → vendor, non-cash) | |
| `PURCHASE_ADJUSTMENT_DECREASE` (vendor → project, non-cash) | |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Balance derivation | `Entity.balance_at` |
| Payables / receivables derivation (issuance + adjustment types) | `payables_at` / `receivables_at` |
| Balance check for real payer funds | `Entity.can_pay` |
| Open period auto-creation | `Entity.save()` |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Purchase wizard (create flow) | `purchase_wizard_view`, `purchase_submit_view` |
| Factory: full create pipeline (items + movements + payment) | `create_from_session` |
| POST parsing/validation | `OperationDataValidator` |
| Reverse view | `operation_reverse_view` |
| Pay view (standalone) | `record_transaction_payment` |
| Adjust view (amount) / adjust items view | `record_accounting_adjustment` / `record_item_adjustment` |
| Move items view (detail-page / inventory shortcut) | `create_inventory_movement` |
| Detail view | `operation_detail_view` |
| URLs (wizard, payment, adjust, item-adjust, detail, reverse) | |
| Templates | |

### 2.6 Tests

| Concern | Test file |
|---------|-----------|
| Create branches | |
| Payment branches | |
| Reversal branches | |
| Movement branches | |
| Adjustment / adjust-items branches | |
| Coverage manifest (executable branch registry) | |

---

## 3. Money flow & entities

- **Source (payer):** a **Project** entity (`_source_role = "url"`). Its fund is the payer fund; `check_balance_on_payment=True` means the project must have enough balance at each payment.
- **Destination (receiver):** a **Vendor** entity (`destination.is_vendor=True`), external (`is_internal=False`), and an **active vendor stakeholder** of the source project (via `Stakeholder`, role `VENDOR`).
- **Transaction flow:**

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `PURCHASE_ISSUANCE` | `project.fund → vendor.fund` | none (issuance, non-cash) |
| 2 | `PURCHASE_PAYMENT` (0..n) | `project.fund → vendor.fund` | ▼ project fund, ▲ vendor fund by payment amount |
| 3 | `PURCHASE_ADJUSTMENT_INCREASE` | `project.fund → vendor.fund` | none (non-cash; raises payable) |
| 4 | `PURCHASE_ADJUSTMENT_DECREASE` | `vendor.fund → project.fund` | none (non-cash; lowers payable) |

- **Payment source fund:** `self.source` (project)
- **Payment target fund:** `self.destination` (vendor)
- **Effect split:** the issuance tx records the obligation once (project payables ↑, vendor receivables ↑); fund balances move **only** on payment.

---

## 4. Settlement model

Derived from `LinkedPaymentTransactionMixin` using `PURCHASE_PAYMENT` transactions only. Because the operation is adjustable, `total_settlable_amount = effective_amount` (amount ± active adjustments).

| Property | After create | After partial pay | After full pay | After reverse |
|----------|--------------|-------------------|----------------|---------------|
| `amount_settled` | `0.00` | `Σ payments` | `== effective_amount` | `0.00` |
| `total_settlable_amount` (`effective_amount`) | `== amount` | unchanged | unchanged | unchanged |
| `amount_remaining_to_settle` | `== amount` | `amount − Σ payments` | `0.00` | `== amount` |
| `is_fully_settled` | `False` | `False` | `True` | `False` |

Payments are **multi-stage**: the purchase is created as a pure obligation; the project then pays the vendor in one or more installments up to the (adjusted) total.

---

## 5. Actions

### 5.1 `create`

Entry points: model `PurchaseOperation.save()` (tests) or the wizard → `PurchaseOperation.create_from_session()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx only — not one-shot).

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source is Project | `source.is_project` | `ValidationError` | `"Purchase source must be a Project entity."` | `clean_source` | |
| VC2 | Destination is Vendor | `destination.is_vendor` | `ValidationError` | `"Purchase destination must be a Vendor entity."` | `clean_destination` | |
| VC3 | Destination not internal | `not destination.is_internal` | `ValidationError` | `"Internal entities cannot be vendors…"` | `clean_destination` | |
| VC4 | Destination is an active vendor stakeholder of the source project | active `Stakeholder(parent=source, target=dest, role=VENDOR)` | `ValidationError` | `"Purchase destination must be an active vendor of the source project."` | `clean_destination` | |
| VC5 | Destination is not a Project | project is not a vendor | `ValidationError` | same as VC2 / VC3 | `clean_destination` | |
| VC6 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | `Operation.clean()` | |
| VC7 | Destination entity active | `destination.active` | `ValidationError` | same as VC6 | `Operation.clean()` | merged with VC4 (inactive vendor) |
| VC8 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | `SourceFundMixin` | |
| VC9 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | `TargetFundMixin` | merged with VC8 |
| VC10 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | |
| VC11 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | `OfficerMixin` | |
| VC12 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | `OfficerMixin` | |
| VC13 | Date not in a closed period (source + destination) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | `Operation.clean()` | covered by period suite |
| VC14 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | `Operation.save()` | covered by period suite |
| VC15 | Balance exempt @ create (issuance unguarded) | not one-shot; issuance is non-cash | never fails | — | `_is_one_shot_operation=False` | |
| VC16 | Tx entity-type contract | `source.is_project` and `target.is_vendor` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | `Transaction.create()` | implied by VC1/VC2 |
| VC17 | Tx operation-type allowed | document is `PURCHASE` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | `Transaction.create()` | implied by VC1/VC2 |
| VC18 | Source ≠ target | project ≠ vendor | always true | `"Source and target funds must be different."` | `Transaction.clean()` | structural (project ≠ vendor) |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | exactly 1 × `PURCHASE_ISSUANCE`, amount `== op.amount`, `project → vendor` | `LinkedIssuanceTransactionMixin.save()` | |
| SC2 | No payment tx on save | not one-shot → `LinkedPaymentTransactionMixin.save()` is a no-op | `LinkedPaymentTransactionMixin.save()` | |
| SC3 | Issuance direction | `tx.source=project.fund`, `tx.target=vendor.fund` | | |
| SC4 | Issuance amount matches | `tx.amount == op.amount` | transaction creation | |
| SC5 | Issuance is non-cash | project fund balance unchanged after save | `Entity.balance_at` | |
| SC6 | Remaining equals full amount | `amount_remaining_to_settle == amount` | `LinkedPaymentTransactionMixin` | |
| SC7 | Not fully settled | `is_fully_settled is False` | `LinkedPaymentTransactionMixin` | |
| SC8 | Project payables ▲ | `project.payables == amount` | `payables_at` | |
| SC9 | Vendor receivables ▲ | `vendor.receivables == amount` | `receivables_at` | |
| SC10 | Project receivables unchanged | `project.receivables == 0` | `receivables_at` | |
| SC11 | Vendor payables unchanged | `vendor.payables == 0` | `payables_at` | |
| SC12 | Invoice items created | one `InvoiceItem` per session item, linked to product template | `create_from_session` | |
| SC13 | Ledger / pending obligation | purchased-but-unreceived item = pending inbound (no movement lines) | `pending_items` | |
| SC14 | Period auto-assigned | `period` = covering period of the source project | `Operation.save()` | covered by period suite |

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | `ReversableModel._validate_can_be_reversed` + view guard | |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | `ReversableModel._validate_can_be_reversed` + view guard | |
| VR3 | No non-reversed payment tx | no `PURCHASE_PAYMENT` exists (payments are explicit, not implicit) | `ValidationError` | `"You can't reverse this object as it has non-reversed transactions…"` | `ReversableModel._requires_transaction_reversal` + `Operation._implicit_reversable_transaction_types` | |
| VR4 | No non-reversed movement lines | all user-driven movements reversed first | `ValidationError` | `"Reverse all inventory movements first."` | `Operation.reverse()` | covered by inventory suite |
| VR5 | No non-reversed adjustments | all adjustments reversed first | `ValidationError` | `"You can't reverse this object as it has non-reversed adjustments…"` | `ReversableModel.reverse()` | covered by adjustment suite |
| VR6 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | `operation_reverse_view` | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | `ReversableModel.reverse()` | |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | `ReversableModel.reverse()` | |
| SR3 | Reversal marked as `is_reversal` | `reversal.reversal_of == original`, not reversed | `ReversableModel` | |
| SR4 | Reversal inherits identity | `amount`, `source`, `destination` copied | `ReversableModel._get_reverse_kwargs` | |
| SR5 | Counter-tx for issuance only | 1 original + 1 counter `PURCHASE_ISSUANCE`; payment blocks reversal | `Operation._implicit_reversable_transaction_types` | |
| SR6 | Counter-tx flips funds | `counter.source == original.target`, `counter.target == original.source` | `Transaction.reverse()` | |
| SR7 | Project fund unchanged | issuance is non-cash; reversal leaves fund balance untouched | `Entity.balance_at` | |
| SR8 | Project payables restored | `project.payables` back to `0.00` | `payables_at` | |
| SR9 | Vendor receivables restored | `vendor.receivables` back to `0.00` | `receivables_at` | |
| SR10 | Differential invariant | create + reverse leaves balances, payables, receivables and ledger unchanged | whole engine | |
| SR11 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | `LinkedIssuanceTransactionMixin.save()` | implied by reversal tests |

### 5.3 `pay`

Standalone action — from the wizard (step 3, initial payment), later from the purchase detail page, or via `record_transaction_payment`. Model entry points: `create_payment_transaction()` / `process_payment()`.

#### 5.3.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VP1 | Balance enforced per payment | `payment_source_fund.can_pay(amount)` | `ValidationError` | `"Insufficient funds: fund balance …"` | `create_payment_transaction` | |
| VP2 | Amount > 0 | `amount > 0` | `ValidationError` | `"The amount should be more than 0"` | `validate_settlement_amount` | |
| VP3 | Amount ≤ remaining (over-payment guard) | `amount <= amount_remaining_to_settle` | `ValidationError` | `"The paid amount … exceeds the remaining …"` | `validate_settlement_amount` | |
| VP4 | Negative blocked | `amount > 0` | `ValidationError` | same as VP2 | `validate_settlement_amount` | |
| VP5 | Partial allowed — multiple payments | `max_payment_transaction_count == -1` | — | — | `LinkedPaymentTransactionMixin` | |
| VP6 | Payment date not in a closed period | `period_entity` open on `date` | `ValidationError` | `"Cannot record a payment dated within a closed financial period."` | `create_payment_transaction` | covered by period suite |

#### 5.3.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SP1 | Payment tx created | 1 × `PURCHASE_PAYMENT`, `project.fund → vendor.fund` | `create_payment_transaction` | |
| SP2 | Remaining decreases | `amount_remaining_to_settle` ↓ by payment | `LinkedPaymentTransactionMixin` | |
| SP3 | Settled accumulates | `amount_settled = Σ payments` | `LinkedPaymentTransactionMixin` | |
| SP4 | Full payment → fully settled | `is_fully_settled`, remaining `0.00` | `LinkedPaymentTransactionMixin` | |
| SP5 | Project fund ▼ | `project.balance` decreases by payment (cash) | `Entity.balance_at` | |
| SP6 | Vendor fund ▲ | `vendor.balance` increases by payment | `Entity.balance_at` | |
| SP7 | Tx count after partial pay | 1 issuance + 1 payment = 2 | — | |

### 5.4 `move items`

Receiving goods into project inventory — from the wizard (step 4), later from the purchase detail page, or from an inventory shortcut via `create_inventory_movement`. The wizard path uses `create_from_session`.

#### 5.4.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VM1 | Operation not reversed; movements enabled | `creates_assets=True`; no active reversal | `ValidationError` | — | `Operation.reverse()` + stock layer | covered by inventory suite |
| VM2 | Qty ≤ item remaining qty | `received_qty ≤ adjusted_quantity − moved` | `ValidationError` | — | `pending_items` / `active_lines_for_item` | covered by inventory suite |
| VM3 | Product allowed + officer valid | product active/obligated; officer staff + active | `ValidationError` | — | `InventoryMovementLine.save()` | covered by inventory suite |

#### 5.4.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SM1 | Movement lines + ledger | `PURCHASE_MOVEMENT` ledger; `InventoryMovementLine` records | `create_from_session` | |
| SM2 | INDIVIDUAL → one line per head | moving 10 animals creates 10 lines of qty 1 (one tagged Product each) | `create_from_session` | |
| SM3 | COMMODITY → one line with full qty | moving 10 kg of corn creates one line qty 10 | `create_from_session` | covered by inventory suite |
| SM4 | Lazy product creation; remaining ↓ | products created by movement line `save()`; item remaining qty ↓ | `InventoryMovementLine.save()` | |
| SM5 | Movement reversible | reversed lines excluded from active stock | `active_lines_for_item` | covered by inventory suite |

### 5.5 `adjust items`

Invoice-item correction (qty / unit price) via `record_item_adjustment`. This is the sanctioned way to change the purchase issuance amount.

#### 5.5.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VA1 | Adjustable + not reversed / not a reversal | `is_items_adjustable=True`; no active reversal | `ValidationError` | — | `InvoiceItemAdjustment` | covered by adjustment suite |
| VA2 | ≥ 1 item changed; qty/price parse | at least one delta, valid decimal | `ValidationError` | — | item-adjustment finalize | covered by adjustment suite |
| VA3 | New qty ≥ already moved | `new_qty ≥ moved_qty` | `ValidationError` | — | item-adjustment finalize | covered by adjustment suite |

#### 5.5.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SA1 | Item adjustment + lines | `InvoiceItemAdjustment` + lines; item adjusted qty/price | `record_item_adjustment` | covered by adjustment suite |
| SA2 | Accounting `Adjustment` + tx | `*_ADJUSTMENT` transaction (non-cash) | `record_item_adjustment` | covered by adjustment suite |
| SA3 | Inventory ledger entries | `*_ADJUSTMENT` ledger entries | `InvoiceItemAdjustment.finalize()` | |

### 5.6 `adjust`

Accounting adjustment on the operation amount via `record_accounting_adjustment`. Adjusting changes `effective_amount` → the total purchase amount, project payables and vendor receivables all change accordingly.

#### 5.6.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VA4 | Adjustable + not reversed / not a reversal | `is_adjustable=True`; no active reversal | `ValidationError` | — | `Adjustment` | covered by adjustment suite |
| VA5 | Adjustment type allowed for PURCHASE | `PURCHASE_RETURN` etc → `PURCHASE_ADJUSTMENT_INCREASE` / `PURCHASE_ADJUSTMENT_DECREASE` | `ValidationError` | — | adjustment type map | covered by adjustment suite |
| VA6 | Amount > 0; officer staff + active | valid amount + officer | `ValidationError` | — | `Adjustment` | covered by adjustment suite |
| VA7 | Reduction can't drive below zero | `effective_amount ≥ 0` after reduction | `ValidationError` | — | `Adjustment` | covered by adjustment suite |

#### 5.6.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SA4 | Adjustment tx (non-cash) + `effective_amount` delta | `PURCHASE_ADJUSTMENT_INCREASE` / `PURCHASE_ADJUSTMENT_DECREASE`; payables/receivables reflect delta | `record_accounting_adjustment` + `AdjustableMixin.effective_amount` | |

### 5.7 Immutability

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
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC14).
- New operations dated inside a **closed** period are rejected (VC13) — `is_date_in_closed_period`.
- **Payments** dated inside a closed period of the governing entity are rejected (VP6) — `create_payment_transaction`.
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period (`_reverse_period`).

---

## 7. Entity roles & balance contract

- **Source:** must be a Project — enforced at model (VC1 `clean_source`) and transaction (VC16 ) layers.
- **Destination:** must be an external Vendor that is an **active vendor stakeholder** of the source project — enforced at model (VC2/VC3/VC4 `clean_destination`) and transaction (VC16) layers. Internal entities are never vendors (VC3); intra-farm transfers go through SALE.
- `project.payables` and `vendor.receivables` are derived from **issuance + adjustment** types (non-cash) — `payables_at` / `receivables_at`.
- `project.balance` and `vendor.balance` are derived exclusively from **payment-type** transactions — `balance_at`.
- The project fund is a **real** fund, so `can_pay()` balance-checks it; `check_balance_on_payment=True` guards each payment (VP1). Issuance itself is unguarded (VC15).

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Create route | Wizard `GET/POST /<project_pk>/purchase/wizard/` (+ `/…/<step>/`, `/cancel/`) → `purchase_wizard_view`; submit → `purchase_submit_view` |
| Source selection | locked to the **Project** from the URL (`_source_role="url"`); no picker |
| Destination selection | active **vendor stakeholders** of the project, **excluding internal entities** (`get_related_entities`); picker + product templates restricted to the project |
| Category | hidden (no category) |
| Amount | derived from invoice-item totals — wizard computes `total_amount`, validated by `_validate_item_totals`; user **cannot** manually edit the amount |
| POST parsing | `OperationDataValidator` |
| Initial payment | wizard step 3 — `amount_paid` (0 allowed); goes through `create_payment_transaction` |
| Record payment (later) | detail-page "Record Payment" → `record_transaction_payment` (URL ); template |
| Move items | wizard step 4, detail-page shortcut, or inventory shortcut → `create_inventory_movement` |
| Adjust / adjust items | `record_accounting_adjustment` / `record_item_adjustment` |
| Detail | `operation_detail_view` — total amount, paid so far, remaining; movement status; "Record Payment", adjust, and reversal actions |
| Reverse | `operation_reverse_view` — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source=project · VC2 dest=vendor · VC3 dest not internal · VC4 dest active vendor stakeholder · VC5 dest not a project · VC6 source active · VC7 dest active · VC8 source fund active · VC9 target fund active · VC10 amount>0 · VC11 officer staff · VC12 officer active · VC13 not closed-period · VC14 covering period · VC15 issuance balance exempt · VC16 tx entity-type · VC17 tx op-type · VC18 source≠target

**create — effects:** SC1 issuance tx only · SC2 no payment tx · SC3 direction project→vendor · SC4 amount matches · SC5 non-cash (fund unchanged) · SC6 remaining == amount · SC7 not fully settled · SC8 project payables ▲ · SC9 vendor receivables ▲ · SC10 project receivables unchanged · SC11 vendor payables unchanged · SC12 invoice items · SC13 ledger/pending obligation · SC14 period assigned

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no payments · VR4 no movements · VR5 no adjustments · VR6 reason required (view)

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 is_reversal · SR4 identity copied · SR5 counter-tx for issuance only · SR6 counter flips funds · SR7 project fund unchanged · SR8 payables restored · SR9 receivables restored · SR10 differential invariant · SR11 reversal owns no txs

**pay — validation:** VP1 balance per payment · VP2 amount>0 · VP3 over-payment guard · VP4 negative blocked · VP5 partial/multiple allowed · VP6 closed-period blocked

**pay — effects:** SP1 payment tx project→vendor · SP2 remaining ↓ · SP3 settled accumulates · SP4 full → fully settled · SP5 project fund ▼ · SP6 vendor fund ▲ · SP7 tx count

**move items — validation:** VM1 not reversed · VM2 qty ≤ remaining · VM3 product/officer valid

**move items — effects:** SM1 movement lines + ledger · SM2 individual → one line per head · SM3 commodity → one line full qty · SM4 lazy products, remaining ↓ · SM5 movement reversible

**adjust items — validation:** VA1 adjustable + not reversed · VA2 ≥1 changed · VA3 qty ≥ moved · **effects:** SA1 item adjustment + lines · SA2 accounting adj + tx · SA3 ledger entries

**adjust — validation:** VA4 adjustable + not reversed · VA5 type allowed · VA6 amount>0/staff · VA7 reduction ≥ 0 · **effects:** SA4 `effective_amount` delta (non-cash)

**immutability:** IM1 source · IM2 destination · IM3 amount (all immutable after save)

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| Issuance tx count | | SC1, SC2 |
| Issuance direction + amount | | SC3, SC4 |
| Issuance non-cash | | SC5, VC15 |
| Settlement after create | | SC6, SC7 |
| Payables / receivables | | SC8–SC11 |
| Source validation | | VC1, VC6, VC8 |
| Destination validation | | VC2, VC5, VC4, VC7 |
| Internal-vendor guard | | VC3 |
| Amount / officer | | VC10–VC12 |
| Immutability | | IM1–IM3 |
| Wizard basic flow | | SC12, SC1, SC3 |
| Wizard movements | | SM2, SM4 |
| Wizard payment | | SP1–SP6 |
| Wizard integrity | | amount-source contract |
| Ledger / pending | | SC13, SM4 |
| Payment happy path | | SP1 |
| Payment settlement | | SP2–SP4, VP5 |
| Payment fund movement | | SP5, SP6 |
| Over-payment / zero / negative | | VP2, VP3, VP4 |
| Balance on payment | | VP1 |
| Tx count | | SP7 |
| Reverse happy path | | SR1–SR4 |
| Reverse counter-tx | | SR5, SR6 |
| Reverse balances/payables | | SR7–SR9 |
| Reverse constraints | | VR1, VR2, VR3 |
| Differential invariant | | SR10 |
| Movement (purchase) | | SM1–SM5, VM1–VM3 |
| Adjust items — ledger | | SA3 |
| Adjust — effective amount | | SA4 |
| Adjust — payables / reverse | | SA4, VR5 |

