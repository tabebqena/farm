# Purchase — Operation Contract

**Epic:** 11.1 — Payable Operations
**Type:** Multi-stage — non-one-shot, partially payable, invoice-based (payable + inventory)
**Actions:** `create`, `pay`, `move items`, `adjust items`, `adjust`, `reverse`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Purchase** operation.
> Every clause below names its implementing code (model → mixin → transaction → view) and its pinning test — as plain names, never links, so renames do not break the spec.
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
| `has_category` | `False` | no financial category |
| `has_repayment` | `False` | no repayment action |
| `has_invoice` | `True` | invoice items + inventory movements |
| `creates_assets` | `True` | received goods enter project inventory |
| `is_adjustable` / `is_items_adjustable` | `True` / `True` | amount + invoice-item adjustments allowed |

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row names the code that must honor it (plain names, no links).

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

### 3.1 World as an ad-hoc vendor

The **World** entity may act as a vendor (no Stakeholder record required), so a
one-off purchase from an unregistered party can be recorded without minting a
throw-away entity. A World purchase is an **ad-hoc, fully-settled one-off**:

- The World is **always offered** as a vendor in the wizard for every project
  (even one with zero vendor Stakeholders); the "no active vendors" hard block is
  removed. `get_related_entities` appends the World entity.
- The purchase **must be paid in full at creation** (step 3 `amount_paid ==
  total`); partial / zero payment is rejected. (The wizard offers no lingering
  payable to the World.)
- Its `PURCHASE_PAYMENT` **cannot be reversed on its own** — the user reverses
  the whole operation, which reverses issuance + payment together
  (`_implicit_reversable_transaction_types`).
- It **cannot be adjusted** (accounting or invoice-item) — the fully-settled
  invariant would otherwise break.
- `counterparty_is_world` (`Operation`) is the single predicate that drives all
  four rules.

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
| VC1 | Source is Project | `source.is_project` | `ValidationError` | `"Purchase source must be a Project entity."` | `clean_source` | `PurchaseCreateTest.test_source_must_be_a_project_entity` |
| VC2 | Destination is Vendor or World | `destination.is_vendor or destination.is_world` | `ValidationError` | `"Purchase destination must be a Vendor entity."` | `clean_destination` | `PurchaseCreateTest.test_destination_must_be_a_vendor_entity` · `WorldPurchaseCreateTest.test_world_vendor_is_accepted` |
| VC3 | Destination not internal | `not destination.is_internal` | `ValidationError` | `"Internal entities cannot be vendors…"` | `clean_destination` | `PurchaseCreateFromSessionTest.test_purchase_rejects_internal_vendor` · `test_get_related_entities_excludes_internal_vendors` |
| VC4 | Destination is an active vendor stakeholder of the source project (skipped for World) | active `Stakeholder(parent=source, target=dest, role=VENDOR)` or `dest.is_world` | `ValidationError` | `"Purchase destination must be an active vendor of the source project."` | `clean_destination` | `PurchaseCreateTest.test_destination_must_be_active_stakeholder_vendor` · `test_destination_with_inactive_stakeholder_raises_validation_error` |
| VC5 | Destination is not a Project | project is not a vendor | `ValidationError` | same as VC2 / VC3 | `clean_destination` | `PurchaseCreateTest.test_destination_project_entity_raises_validation_error` |
| VC6 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | `Operation.clean()` | `PurchaseCreateTest.test_source_must_be_active` |
| VC7 | Destination entity active | `destination.active` | `ValidationError` | same as VC6 | `Operation.clean()` | merged with VC4 (inactive vendor) |
| VC8 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | `SourceFundMixin` | `PurchaseCreateTest.test_source_fund_must_be_active` |
| VC9 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | `TargetFundMixin` | merged with VC8 |
| VC10 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | `PurchaseCreateTest.test_amount_zero_raises_validation_error` · `test_amount_negative_raises_validation_error` |
| VC11 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | `OfficerMixin` | `PurchaseCreateTest.test_officer_user_must_be_staff` |
| VC12 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | `OfficerMixin` | `PurchaseCreateTest.test_officer_must_be_active` |
| VC13 | Date not in a closed period (source + destination) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | `Operation.clean()` | shared period suite (`OperationPeriodAssignmentTest.test_operation_in_closed_period_raises`) |
| VC14 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | `Operation.save()` | shared period suite (`OperationPeriodAssignmentTest.test_operation_raises_when_no_open_period`) |
| VC15 | Balance exempt @ create (issuance unguarded) | not one-shot; issuance is non-cash | never fails | — | `_is_one_shot_operation=False` | structural (see `test_project_fund_balance_unchanged_after_save`) |
| VC16 | Tx entity-type contract | `source.is_project` and (`target.is_vendor` or `target.is_world`) | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | `Transaction.create()` | implied by VC1/VC2 · `WorldPurchaseCreateTest.test_type_map_accepts_world_for_purchase` |
| VC17 | Tx operation-type allowed | document is `PURCHASE` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | `Transaction.create()` | implied by VC1/VC2 |
| VC18 | Source ≠ target | project ≠ vendor | always true | `"Source and target funds must be different."` | `Transaction.clean()` | structural (project ≠ vendor) |
| VC19 | World purchase fully paid at creation | if `destination.is_world` then `amount_paid == total` | `ValidationError` | `"A purchase from the World must be paid in full at creation."` | `create_from_session` | `WorldPurchaseCreateTest.test_create_from_session_full_payment_succeeds` · `test_create_from_session_zero_payment_rejected` · `test_create_from_session_partial_payment_rejected` |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | exactly 1 × `PURCHASE_ISSUANCE`, amount `== op.amount`, `project → vendor` | `LinkedIssuanceTransactionMixin.save()` | `PurchaseCreateTest.test_save_creates_exactly_one_issuance_transaction` |
| SC2 | No payment tx on save | not one-shot → `LinkedPaymentTransactionMixin.save()` is a no-op | `LinkedPaymentTransactionMixin.save()` | `PurchaseCreateTest.test_no_payment_transaction_created_on_save` |
| SC3 | Issuance direction | `tx.source=project.fund`, `tx.target=vendor.fund` | | `PurchaseCreateTest.test_issuance_transaction_direction_is_project_to_vendor` |
| SC4 | Issuance amount matches | `tx.amount == op.amount` | transaction creation | `PurchaseCreateTest.test_issuance_transaction_amount_matches_operation` |
| SC5 | Issuance is non-cash | project fund balance unchanged after save | `Entity.balance_at` | `PurchaseCreateTest.test_project_fund_balance_unchanged_after_save` |
| SC6 | Remaining equals full amount | `amount_remaining_to_settle == amount` | `LinkedPaymentTransactionMixin` | `PurchaseCreateTest.test_amount_remaining_to_settle_equals_full_amount_after_creation` |
| SC7 | Not fully settled | `is_fully_settled is False` | `LinkedPaymentTransactionMixin` | `PurchaseCreateTest.test_is_not_fully_settled_after_creation` |
| SC8 | Project payables ▲ | `project.payables == amount` | `payables_at` | `PurchaseCreateTest.test_create_project_payables_increase` |
| SC9 | Vendor receivables ▲ | `vendor.receivables == amount` | `receivables_at` | `PurchaseCreateTest.test_create_vendor_receivables_increase` |
| SC10 | Project receivables unchanged | `project.receivables == 0` | `receivables_at` | `PurchaseCreateTest.test_create_project_receivables_unchanged` |
| SC11 | Vendor payables unchanged | `vendor.payables == 0` | `payables_at` | `PurchaseCreateTest.test_create_vendor_payables_unchanged` |
| SC12 | Invoice items created | one `InvoiceItem` per session item, linked to product template | `create_from_session` | `PurchaseCreateFromSessionTest.test_create_from_session_basic` · `test_create_from_session_multiple_items` |
| SC13 | Ledger / pending obligation | purchased-but-unreceived item = pending inbound (no movement lines) | `pending_items` | `PurchaseCreateFromSessionTest.test_create_from_session_ledger_entries_created` · `StockPendingItemsTest.test_pending_inbound_for_unreceived_purchase` |
| SC14 | Period auto-assigned | `period` = covering period of the source project | `Operation.save()` | shared period suite (`OperationPeriodAssignmentTest`) |

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | `ReversableModel._validate_can_be_reversed` + view guard | `PurchaseReversalTest.test_cannot_reverse_already_reversed_operation` |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | `ReversableModel._validate_can_be_reversed` + view guard | `PurchaseReversalTest.test_cannot_reverse_a_reversal` |
| VR3 | No non-reversed payment tx (World purchase exempt) | no explicit `PURCHASE_PAYMENT` exists (payments are explicit, not implicit) — a World purchase's payment **is implicit** and does not block | `ValidationError` | `"You can't reverse this object as it has non-reversed transactions…"` | `ReversableModel._requires_transaction_reversal` + `Operation._implicit_reversable_transaction_types` | `PurchaseReversalTest.test_reversal_blocked_when_payment_exists` · `test_reversible_after_payment_reversed` · `WorldPurchaseCreateTest.test_operation_reversal_reverses_issuance_and_payment` |
| VR4 | No non-reversed movement lines | all user-driven movements reversed first | `ValidationError` | `"Reverse all inventory movements first."` | `Operation.reverse()` | `PurchaseReversalAfterMovementsTest.test_reversal_blocked_while_movement_active` · `test_reversible_after_all_movements_reversed` |
| VR5 | No non-reversed adjustments | all adjustments reversed first | `ValidationError` | `"You can't reverse this object as it has non-reversed adjustments…"` | `ReversableModel.reverse()` | covered by adjustment suite (`AdjustmentReversalTest`) |
| VR6 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | `operation_reverse_view` | view contract (see §8) |
| VR7 | World payment not reversible alone | a standalone `PURCHASE_PAYMENT` reversal on a World purchase is rejected (transaction-level view) | view redirect + message | `"This payment involves the World and cannot be reversed alone…"` | `transaction_reverse_view` + `TransactionDetailView.can_reverse` | `WorldPurchaseViewTest.test_world_payment_cannot_be_reversed_alone` · `test_world_payment_detail_hides_reverse` |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | `ReversableModel.reverse()` | `PurchaseReversalTest.test_reverse_creates_reversal_operation` |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | `ReversableModel.reverse()` | `PurchaseReversalTest.test_reverse_marks_original_as_reversed` |
| SR3 | Reversal marked as `is_reversal` | `reversal.reversal_of == original`, not reversed | `ReversableModel` | `PurchaseReversalTest.test_reversal_is_marked_as_reversal` |
| SR4 | Reversal inherits identity | `amount`, `source`, `destination` copied | `ReversableModel._get_reverse_kwargs` | `PurchaseReversalTest.test_reverse_inherits_amount_source_destination` |
| SR5 | Counter-tx for issuance only | 1 original + 1 counter `PURCHASE_ISSUANCE`; payment blocks reversal | `Operation._implicit_reversable_transaction_types` | `PurchaseReversalTest.test_reverse_creates_counter_transaction_for_issuance` · `test_reversible_after_payment_reversed_counter_for_issuance_only` |
| SR6 | Counter-tx flips funds | `counter.source == original.target`, `counter.target == original.source` | `Transaction.reverse()` | `PurchaseReversalTest.test_reverse_counter_transaction_flips_funds` |
| SR7 | Project fund unchanged | issuance is non-cash; reversal leaves fund balance untouched | `Entity.balance_at` | `PurchaseReversalTest.test_project_fund_unchanged_after_reversal` |
| SR8 | Project payables restored | `project.payables` back to `0.00` | `payables_at` | `PurchaseReversalTest.test_reverse_restores_project_payables` |
| SR9 | Vendor receivables restored | `vendor.receivables` back to `0.00` | `receivables_at` | `PurchaseReversalTest.test_reverse_restores_vendor_receivables` |
| SR10 | Differential invariant | create + reverse leaves balances, payables, receivables and ledger unchanged | whole engine | `PurchaseReversalTest.test_create_then_reverse_leaves_world_unchanged` · `test_pay_reverse_payment_then_reverse_op_leaves_world_unchanged` · `PurchaseReversalAfterMovementsTest.test_reverse_after_movements_reversed_leaves_world_unchanged` |
| SR11 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | `LinkedIssuanceTransactionMixin.save()` | implied by reversal tests |

### 5.3 `pay`

Standalone action — from the wizard (step 3, initial payment), later from the purchase detail page, or via `record_transaction_payment`. Model entry points: `create_payment_transaction()` / `process_payment()`.

#### 5.3.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VP1 | Balance enforced per payment | `payment_source_fund.can_pay(amount)` | `ValidationError` | `"Insufficient funds: fund balance …"` | `create_payment_transaction` | `PurchasePaymentTest.test_payment_blocked_when_project_fund_has_insufficient_balance` · `test_check_balance_on_payment_is_enabled` |
| VP2 | Amount > 0 | `amount > 0` | `ValidationError` | `"The amount should be more than 0"` | `validate_settlement_amount` | `PurchasePaymentTest.test_zero_payment_raises_validation_error` · `test_negative_payment_raises_validation_error` |
| VP3 | Amount ≤ remaining (over-payment guard) | `amount <= amount_remaining_to_settle` | `ValidationError` | `"The paid amount … exceeds the remaining …"` | `validate_settlement_amount` | `PurchasePaymentTest.test_payment_exceeding_operation_amount_raises_validation_error` · `test_partial_payment_then_over_payment_raises_validation_error` |
| VP4 | Negative blocked | `amount > 0` | `ValidationError` | same as VP2 | `validate_settlement_amount` | `PurchasePaymentTest.test_negative_payment_raises_validation_error` |
| VP5 | Partial allowed — multiple payments | `max_payment_transaction_count == -1` | — | — | `LinkedPaymentTransactionMixin` | `PurchasePaymentTest.test_multiple_partial_payments_are_allowed` |
| VP6 | Payment date not in a closed period | `period_entity` open on `date` | `ValidationError` | `"Cannot record a payment dated within a closed financial period."` | `create_payment_transaction` | shared period suite (`DownstreamClosedPeriodGuardTest.test_payment_rejected_in_closed_period`) |
| VP7 | World counterparty must settle in full | if `counterparty_is_world` then `amount == amount_remaining_to_settle` (and, in `process_payment`, `== amount`) | `ValidationError` / `ValueError` | `"An operation whose counterparty is the World must be settled in full…"` | `create_payment_transaction` / `process_payment` | `WorldPurchaseCreateTest.test_process_payment_partial_rejected` · `test_create_payment_transaction_partial_rejected` |

#### 5.3.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SP1 | Payment tx created | 1 × `PURCHASE_PAYMENT`, `project.fund → vendor.fund` | `create_payment_transaction` | `PurchasePaymentTest.test_payment_creates_purchase_payment_transaction` |
| SP2 | Remaining decreases | `amount_remaining_to_settle` ↓ by payment | `LinkedPaymentTransactionMixin` | `PurchasePaymentTest.test_amount_remaining_to_settle_decreases_after_payment` |
| SP3 | Settled accumulates | `amount_settled = Σ payments` | `LinkedPaymentTransactionMixin` | `PurchasePaymentTest.test_multiple_payments_accumulate_correctly` |
| SP4 | Full payment → fully settled | `is_fully_settled`, remaining `0.00` | `LinkedPaymentTransactionMixin` | `PurchasePaymentTest.test_full_payment_marks_operation_as_fully_settled` |
| SP5 | Project fund ▼ | `project.balance` decreases by payment (cash) | `Entity.balance_at` | `PurchasePaymentTest.test_project_fund_decreases_by_payment_amount` |
| SP6 | Vendor fund ▲ | `vendor.balance` increases by payment | `Entity.balance_at` | `PurchasePaymentTest.test_vendor_fund_increases_by_payment_amount` |
| SP7 | Tx count after partial pay | 1 issuance + 1 payment = 2 | — | `PurchasePaymentTest.test_total_transactions_after_partial_payment_is_two` |

### 5.4 `move items`

Receiving goods into project inventory — from the wizard (step 4), later from the purchase detail page, or from an inventory shortcut via `create_inventory_movement`. The wizard path uses `create_from_session`.

#### 5.4.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VM1 | Operation not reversed; movements enabled | `creates_assets=True`; no active reversal | `ValidationError` | — | `Operation.reverse()` + stock layer | covered by inventory suite (`PurchaseReversalAfterMovementsTest.test_reversal_blocked_while_movement_active`) |
| VM2 | Qty ≤ item remaining qty | `received_qty ≤ adjusted_quantity − moved` | `ValidationError` | — | `pending_items` / `active_lines_for_item` | `InventoryMovementCreationTest.test_quantity_exceeds_invoice_item` |
| VM3 | Product allowed + officer valid | product active/obligated; officer staff + active | `ValidationError` | — | `InventoryMovementLine.save()` | `InventoryMovementCreationTest.test_non_staff_cannot_create_movement` |

#### 5.4.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SM1 | Movement lines + ledger | `PURCHASE_MOVEMENT` ledger; `InventoryMovementLine` records | `create_from_session` | `InventoryMovementCreationTest.test_create_inventory_movement_purchase` · `PurchaseCreateFromSessionTest.test_create_from_session_ledger_entries_created` |
| SM2 | INDIVIDUAL → one line per head | moving 10 animals creates 10 lines of qty 1 (one tagged Product each) | `create_from_session` | `InventoryMovementCreationTest.test_purchase_movement_creates_new_product_per_animal` · `test_purchase_lazy_product_belongs_to_project` |
| SM3 | COMMODITY → one line with full qty | moving 10 kg of corn creates one line qty 10 | `create_from_session` | `InventoryMovementModelContractTest.test_purchase_commodity_receives_single_line_full_qty` |
| SM4 | Lazy product creation; remaining ↓ | products created by movement line `save()`; item remaining qty ↓ | `InventoryMovementLine.save()` | `InventoryMovementCreationTest.test_purchase_lazy_product_belongs_to_project` · `StockPendingItemsTest.test_no_pending_for_received_purchase` |
| SM5 | Movement reversible | reversed lines excluded from active stock | `active_lines_for_item` | `MovementActionViewsTest.test_reverse_movement_line_success` · `test_batch_reverse_success` |

### 5.5 `adjust items`

Invoice-item correction (qty / unit price) via `record_item_adjustment`. This is the sanctioned way to change the purchase issuance amount.

#### 5.5.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VA1 | Adjustable + not reversed / not a reversal | `is_items_adjustable=True`; no active reversal | `ValidationError` | — | `InvoiceItemAdjustment` | `ValidationTest.test_item_adjustment_requires_purchase_or_sale` · `test_type_must_match_operation` |
| VA2 | ≥ 1 item changed; qty/price parse | at least one delta, valid decimal | `ValidationError` | — | item-adjustment finalize | `ValidationTest.test_line_requires_at_least_one_change_field` · `test_line_must_belong_to_same_operation` |
| VA3 | New qty ≥ already moved | `new_qty ≥ moved_qty` | `ValidationError` | — | `InvoiceItemAdjustmentLine.clean` | `DecreaseWithMovementsTest.test_decrease_below_moved_quantity_raises` · `test_decrease_to_moved_quantity_succeeds` (see note in Sale spec) |
| VA8 | Not a World purchase | `not operation.counterparty_is_world` | `ValidationError` | `"A purchase from the World cannot be adjusted."` | `InvoiceItemAdjustment.clean` + `RecordItemAdjustmentView` guard | `WorldPurchaseAdjustmentBlockTest.test_item_adjustment_blocked` |

#### 5.5.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SA1 | Item adjustment + lines | `InvoiceItemAdjustment` + lines; item adjusted qty/price | `record_item_adjustment` | `FinalizationTest.test_finalize_purchase_decrease_creates_correct_adjustment` · `test_finalize_purchase_increase_creates_correct_adjustment` |
| SA2 | Accounting `Adjustment` + tx | `*_ADJUSTMENT` transaction (non-cash) | `record_item_adjustment` | `FinalizationTest.test_finalize_creates_issuance_transaction` · `test_finalize_reflects_in_effective_amount` |
| SA3 | Inventory ledger entries | `*_ADJUSTMENT` ledger entries | `InvoiceItemAdjustment.finalize()` | `LedgerEntryTest.test_purchase_price_decrease_ledger_entry` · `test_purchase_quantity_decrease_ledger_entry` · `test_purchase_removal_ledger_entry` |

### 5.6 `adjust`

Accounting adjustment on the operation amount via `record_accounting_adjustment`. Adjusting changes `effective_amount` → the total purchase amount, project payables and vendor receivables all change accordingly.

#### 5.6.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VA4 | Adjustable + not reversed / not a reversal | `is_adjustable=True`; no active reversal | `ValidationError` | — | `Adjustment` | `AdjustmentValidationTest.test_purchase_operation_is_adjustable` · `AdjustmentReversalTest.test_cannot_reverse_already_reversed_adjustment` · `test_cannot_reverse_a_reversal` |
| VA5 | Adjustment type allowed for PURCHASE | `PURCHASE_RETURN` etc → `PURCHASE_ADJUSTMENT_INCREASE` / `PURCHASE_ADJUSTMENT_DECREASE` | `ValidationError` | — | adjustment type map | `AdjustmentDirectionTest.test_purchase_return_reverses_direction` · `test_purchase_undercharge_keeps_direction` |
| VA6 | Amount > 0; officer staff + active | valid amount + officer | `ValidationError` | — | `Adjustment` | `AdjustmentValidationTest.test_amount_zero_raises_validation_error` · `test_amount_negative_raises_validation_error` · `test_officer_user_must_be_staff` · `test_officer_must_be_active` |
| VA7 | Reduction can't drive below zero | `effective_amount ≥ 0` after reduction | `ValidationError` | — | `Adjustment` | `AdjustmentEffectiveAmountTest.test_single_decrease_reduces_effective_amount` (floor enforced by engine) |
| VA9 | Not a World purchase | `not operation.counterparty_is_world` | `ValidationError` | `"A purchase from the World cannot be adjusted."` | `Adjustment.clean` + `RecordAccountingAdjustmentView` guard | `WorldPurchaseAdjustmentBlockTest.test_accounting_adjustment_blocked` |

#### 5.6.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SA4 | Adjustment tx (non-cash) + `effective_amount` delta | `PURCHASE_ADJUSTMENT_INCREASE` / `PURCHASE_ADJUSTMENT_DECREASE`; payables/receivables reflect delta | `record_accounting_adjustment` + `AdjustableMixin.effective_amount` | `AdjustmentTransactionTest.test_purchase_adjustment_creates_purchase_adjustment_transaction` · `AdjustmentEffectiveAmountTest.test_single_decrease_reduces_effective_amount` · `test_single_increase_raises_effective_amount` · `AdjustmentReversalTest.test_purchase_return_reduces_project_payables` · `test_purchase_return_reduces_vendor_receivables` |

### 5.7 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by `ImmutableMixin` via `_immutable_fields`.

| Branch | Enforced by | Pinned by test |
|--------|-------------|----------------|
| `source` changed after save | `ImmutableMixin.save()` | `PurchaseCreateTest.test_source_is_immutable_after_save` |
| `destination` changed after save | `ImmutableMixin.save()` | `PurchaseCreateFromSessionTest.test_destination_is_immutable_after_save` |
| `amount` changed after save | `ImmutableMixin.save()` | `PurchaseCreateFromSessionTest.test_amount_is_immutable_after_save` |

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
- **Destination:** must be an external Vendor that is an **active vendor stakeholder** of the source project — enforced at model (VC2/VC3/VC4 `clean_destination`) and transaction (VC16) layers. Internal entities are never vendors (VC3); intra-farm transfers go through SALE. The **World** entity is the one exception: it is accepted without a Stakeholder record as an ad-hoc, fully-settled one-off (§3.1).
- `project.payables` and `vendor.receivables` are derived from **issuance + adjustment** types (non-cash) — `payables_at` / `receivables_at`.
- `project.balance` and `vendor.balance` are derived exclusively from **payment-type** transactions — `balance_at`.
- The project fund is a **real** fund, so `can_pay()` balance-checks it; `check_balance_on_payment=True` guards each payment (VP1). Issuance itself is unguarded (VC15).

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Create route | Wizard `GET/POST /<project_pk>/purchase/wizard/` (+ `/…/<step>/`, `/cancel/`) → `purchase_wizard_view`; submit → `purchase_submit_view` |
| Source selection | locked to the **Project** from the URL (`_source_role="url"`); no picker |
| Destination selection | active **vendor stakeholders** of the project, **excluding internal entities**, **plus the World** (`get_related_entities`, always available — no "no vendors" block); picker + product templates restricted to the project |
| Category | hidden (no category) |
| Amount | derived from invoice-item totals — wizard computes `total_amount`, validated by `_validate_item_totals`; user **cannot** manually edit the amount |
| POST parsing | `OperationDataValidator` |
| Initial payment | wizard step 3 — `amount_paid` (0 allowed for normal vendors; **must equal the total for a World vendor**, VC19/VP7); goes through `create_payment_transaction` |
| Record payment (later) | detail-page "Record Payment" → `record_transaction_payment` (URL ); template |
| Move items | wizard step 4, detail-page shortcut, or inventory shortcut → `create_inventory_movement` |
| Adjust / adjust items | `record_accounting_adjustment` / `record_item_adjustment` (both hidden + rejected for a World purchase, VA8/VA9) |
| Detail | `operation_detail_view` — total amount, paid so far, remaining; movement status; "Record Payment", adjust, and reversal actions |
| Reverse | `operation_reverse_view` — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source=project · VC2 dest=vendor or World · VC3 dest not internal · VC4 dest active vendor stakeholder (skipped for World) · VC5 dest not a project · VC6 source active · VC7 dest active · VC8 source fund active · VC9 target fund active · VC10 amount>0 · VC11 officer staff · VC12 officer active · VC13 not closed-period · VC14 covering period · VC15 issuance balance exempt · VC16 tx entity-type · VC17 tx op-type · VC18 source≠target · VC19 World purchase fully paid at creation

**create — effects:** SC1 issuance tx only · SC2 no payment tx · SC3 direction project→vendor · SC4 amount matches · SC5 non-cash (fund unchanged) · SC6 remaining == amount · SC7 not fully settled · SC8 project payables ▲ · SC9 vendor receivables ▲ · SC10 project receivables unchanged · SC11 vendor payables unchanged · SC12 invoice items · SC13 ledger/pending obligation · SC14 period assigned

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no payments (World payment implicit) · VR4 no movements · VR5 no adjustments · VR6 reason required (view) · VR7 World payment not reversible alone

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 is_reversal · SR4 identity copied · SR5 counter-tx for issuance only (issuance + payment for World) · SR6 counter flips funds · SR7 project fund unchanged · SR8 payables restored · SR9 receivables restored · SR10 differential invariant · SR11 reversal owns no txs

**pay — validation:** VP1 balance per payment · VP2 amount>0 · VP3 over-payment guard · VP4 negative blocked · VP5 partial/multiple allowed · VP6 closed-period blocked · VP7 World counterparty settles in full

**pay — effects:** SP1 payment tx project→vendor · SP2 remaining ↓ · SP3 settled accumulates · SP4 full → fully settled · SP5 project fund ▼ · SP6 vendor fund ▲ · SP7 tx count

**move items — validation:** VM1 not reversed · VM2 qty ≤ remaining · VM3 product/officer valid

**move items — effects:** SM1 movement lines + ledger · SM2 individual → one line per head · SM3 commodity → one line full qty · SM4 lazy products, remaining ↓ · SM5 movement reversible

**adjust items — validation:** VA1 adjustable + not reversed · VA2 ≥1 changed · VA3 qty ≥ moved · VA8 not a World purchase · **effects:** SA1 item adjustment + lines · SA2 accounting adj + tx · SA3 ledger entries

**adjust — validation:** VA4 adjustable + not reversed · VA5 type allowed · VA6 amount>0/staff · VA7 reduction ≥ 0 · VA9 not a World purchase · **effects:** SA4 `effective_amount` delta (non-cash)

**immutability:** IM1 source · IM2 destination · IM3 amount (all immutable after save)

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| Issuance tx count | `PurchaseCreateTest.test_save_creates_exactly_one_issuance_transaction` · `test_no_payment_transaction_created_on_save` | SC1, SC2 |
| Issuance direction + amount | `PurchaseCreateTest.test_issuance_transaction_direction_is_project_to_vendor` · `test_issuance_transaction_amount_matches_operation` | SC3, SC4 |
| Issuance non-cash | `PurchaseCreateTest.test_project_fund_balance_unchanged_after_save` | SC5, VC15 |
| Settlement after create | `PurchaseCreateTest.test_amount_remaining_to_settle_equals_full_amount_after_creation` · `test_is_not_fully_settled_after_creation` | SC6, SC7 |
| Payables / receivables | `PurchaseCreateTest.test_create_project_payables_increase` · `test_create_vendor_receivables_increase` · `test_create_project_receivables_unchanged` · `test_create_vendor_payables_unchanged` | SC8–SC11 |
| Source validation | `PurchaseCreateTest.test_source_must_be_a_project_entity` · `test_source_must_be_active` · `test_source_fund_must_be_active` | VC1, VC6, VC8 |
| Destination validation | `PurchaseCreateTest.test_destination_must_be_a_vendor_entity` · `test_destination_project_entity_raises_validation_error` · `test_destination_must_be_active_stakeholder_vendor` · `test_destination_with_inactive_stakeholder_raises_validation_error` | VC2, VC5, VC4, VC7 |
| Internal-vendor guard | `PurchaseCreateFromSessionTest.test_purchase_rejects_internal_vendor` · `test_get_related_entities_excludes_internal_vendors` | VC3 |
| Amount / officer | `PurchaseCreateTest.test_amount_zero_raises_validation_error` · `test_amount_negative_raises_validation_error` · `test_officer_user_must_be_staff` · `test_officer_must_be_active` | VC10–VC12 |
| Immutability | `PurchaseCreateTest.test_source_is_immutable_after_save` · `PurchaseCreateFromSessionTest.test_destination_is_immutable_after_save` · `test_amount_is_immutable_after_save` | IM1–IM3 |
| Wizard basic flow | `PurchaseCreateFromSessionTest.test_create_from_session_basic` · `test_create_from_session_multiple_items` · `test_create_from_session_creates_issuance_transaction` · `test_create_from_session_full_flow` | SC12, SC1, SC3 |
| Wizard movements | `PurchaseCreateFromSessionTest.test_create_from_session_with_received_qty` · `test_create_from_session_partial_received_qty` | SM2, SM4 |
| Wizard payment | `PurchaseCreateFromSessionTest.test_create_from_session_with_payment` · `test_create_from_session_zero_payment` · `test_create_from_session_full_payment` | SP1–SP6 |
| Wizard integrity | `PurchaseCreateFromSessionTest.test_create_from_session_item_totals_mismatch` · `test_create_from_session_item_totals_slight_mismatch` · `test_create_from_session_item_totals_within_tolerance` · `test_create_from_session_missing_vendor_raises_error` · `test_create_from_session_payment_exceeds_total` · `test_create_from_session_missing_items_raises_error` · `test_create_from_session_empty_items_raises_error` | amount-source contract |
| Ledger / pending | `PurchaseCreateFromSessionTest.test_create_from_session_ledger_entries_created` · `StockPendingItemsTest.test_pending_inbound_for_unreceived_purchase` | SC13, SM4 |
| Payment happy path | `PurchasePaymentTest.test_payment_creates_purchase_payment_transaction` | SP1 |
| Payment settlement | `PurchasePaymentTest.test_amount_remaining_to_settle_decreases_after_payment` · `test_multiple_payments_accumulate_correctly` · `test_full_payment_marks_operation_as_fully_settled` · `test_multiple_partial_payments_are_allowed` | SP2–SP4, VP5 |
| Payment fund movement | `PurchasePaymentTest.test_project_fund_decreases_by_payment_amount` · `test_vendor_fund_increases_by_payment_amount` | SP5, SP6 |
| Over-payment / zero / negative | `PurchasePaymentTest.test_payment_exceeding_operation_amount_raises_validation_error` · `test_partial_payment_then_over_payment_raises_validation_error` · `test_zero_payment_raises_validation_error` · `test_negative_payment_raises_validation_error` | VP2, VP3, VP4 |
| Balance on payment | `PurchasePaymentTest.test_payment_blocked_when_project_fund_has_insufficient_balance` · `test_check_balance_on_payment_is_enabled` | VP1 |
| Tx count | `PurchasePaymentTest.test_total_transactions_after_partial_payment_is_two` | SP7 |
| Reverse happy path | `PurchaseReversalTest.test_reverse_creates_reversal_operation` · `test_reverse_marks_original_as_reversed` · `test_reversal_is_marked_as_reversal` · `test_reverse_inherits_amount_source_destination` | SR1–SR4 |
| Reverse counter-tx | `PurchaseReversalTest.test_reverse_creates_counter_transaction_for_issuance` · `test_reverse_counter_transaction_flips_funds` · `test_reversible_after_payment_reversed_counter_for_issuance_only` | SR5, SR6 |
| Reverse balances/payables | `PurchaseReversalTest.test_project_fund_unchanged_after_reversal` · `test_reverse_restores_project_payables` · `test_reverse_restores_vendor_receivables` | SR7–SR9 |
| Reverse constraints | `PurchaseReversalTest.test_reversal_blocked_when_payment_exists` · `test_cannot_reverse_already_reversed_operation` · `test_cannot_reverse_a_reversal` · `test_reversible_after_payment_reversed` | VR1, VR2, VR3 |
| Differential invariant | `PurchaseReversalTest.test_create_then_reverse_leaves_world_unchanged` · `test_pay_reverse_payment_then_reverse_op_leaves_world_unchanged` · `PurchaseReversalAfterMovementsTest.test_reverse_after_movements_reversed_leaves_world_unchanged` | SR10 |
| Movement (purchase) | `InventoryMovementCreationTest.test_create_inventory_movement_purchase` · `test_purchase_movement_creates_new_product_per_animal` · `test_purchase_commodity_receives_single_line_full_qty` · `test_purchase_lazy_product_belongs_to_project` · `test_quantity_exceeds_invoice_item` · `test_non_staff_cannot_create_movement` | SM1–SM5, VM1–VM3 |
| Adjust items — ledger | `LedgerEntryTest.test_purchase_price_decrease_ledger_entry` · `test_purchase_quantity_decrease_ledger_entry` · `test_purchase_removal_ledger_entry` · `test_idempotency_key_prevents_duplicate_entries` | SA3 |
| Adjust — effective amount | `AdjustmentTransactionTest.test_purchase_adjustment_creates_purchase_adjustment_transaction` · `AdjustmentEffectiveAmountTest.test_single_decrease_reduces_effective_amount` · `test_single_increase_raises_effective_amount` · `test_reversed_adjustment_excluded_from_effective_amount` | SA4 |
| Adjust — payables / reverse | `AdjustmentReversalTest.test_purchase_return_reduces_project_payables` · `test_reverse_adjustment_restores_project_payables` · `test_reverse_adjustment_restores_vendor_receivables` | SA4, VR5 |
| World vendor (ad-hoc) | `WorldPurchaseCreateTest.test_world_vendor_is_accepted` · `test_get_related_entities_includes_world` · `test_wizard_vendor_queryset_includes_world` · `test_type_map_accepts_world_for_purchase` | VC2, VC4, VC16 |
| World full settlement | `WorldPurchaseCreateTest.test_create_from_session_full_payment_succeeds` · `test_create_from_session_zero_payment_rejected` · `test_create_from_session_partial_payment_rejected` · `test_process_payment_partial_rejected` · `test_create_payment_transaction_partial_rejected` | VC19, VP7 |
| World reversal | `WorldPurchaseCreateTest.test_operation_reversal_reverses_issuance_and_payment` · `test_create_pay_reverse_leaves_world_unchanged` · `WorldPurchaseViewTest.test_world_payment_cannot_be_reversed_alone` · `test_world_payment_detail_hides_reverse` · `test_wizard_available_without_vendor_stakeholders` | VR3, VR7, SR5, SR10 |
| World adjustments blocked | `WorldPurchaseAdjustmentBlockTest.test_accounting_adjustment_blocked` · `test_item_adjustment_blocked` | VA8, VA9 |

