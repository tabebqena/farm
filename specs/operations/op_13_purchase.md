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
| Operation type | `OperationType.PURCHASE` (`"PURCHASE"`) | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:13) |
| Proxy class | `PurchaseOperation` | [`op_purchase.py`](../../apps/app_operation/models/proxies/op_purchase.py:13) |
| URL slug | `"purchase"` | [`op_purchase.py`](../../apps/app_operation/models/proxies/op_purchase.py:17) |
| Label | `"Purchase Issuance"` | [`op_purchase.py`](../../apps/app_operation/models/proxies/op_purchase.py:18) |
| Theme | n/a — not defined on proxy (defaults) | [`op_purchase.py`](../../apps/app_operation/models/proxies/op_purchase.py:13) |
| Source role | `url` (a Project entity) | [`op_purchase.py`](../../apps/app_operation/models/proxies/op_purchase.py:19) |
| Destination role | `post` (a Vendor entity, selected) | [`op_purchase.py`](../../apps/app_operation/models/proxies/op_purchase.py:20) |
| Registered in | `PROXY_MAP` | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:35) |
| Cross-op reference | row PU | [`operations-comparison.md`](operations-comparison.md:211) |

**Configuration flags** (all on [`op_purchase.py`](../../apps/app_operation/models/proxies/op_purchase.py:13)):

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
| Proxy class + type-specific config + `clean_source`/`clean_destination` + `create_from_session` | [`op_purchase.py`](../../apps/app_operation/models/proxies/op_purchase.py:13) |
| Proxy registry / URL→class resolution | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:35) |
| Shared `Operation` engine (`clean`, `save`, `reverse`, `process_payment`, period assignment, reversable tx types) | [`operation.py`](../../apps/app_operation/models/operation.py:34) |
| Operation type enum | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:13) |

### 2.2 Core engine (mixins / base)

| Concern | Implementing code |
|---------|-------------------|
| Immutability of `source`/`destination`/`amount`/`period` | [`ImmutableMixin`](../../apps/app_base/mixins.py:30) + `_immutable_fields` in [`operation.py`](../../apps/app_operation/models/operation.py:51) |
| Amount must be > 0 | [`AmountCleanMixin`](../../apps/app_base/mixins.py:64) |
| Officer must be staff + active | [`OfficerMixin`](../../apps/app_base/mixins.py:80) |
| Source fund exists + active | [`SourceFundMixin`](../../apps/app_base/mixins.py:127) |
| Target fund exists + active | [`TargetFundMixin`](../../apps/app_base/mixins.py:147) |
| Issuance tx creation on save (skipped for reversals) | [`LinkedIssuanceTransactionMixin`](../../apps/app_base/mixins.py:184) |
| Payment / settlement (`amount_settled`, `remaining`, `is_fully_settled`, balance check, over-payment guard) | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:242) |
| Repayment | n/a — `has_repayment=False` |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | [`ReversableModel`](../../apps/app_base/models.py:133) + [`Operation.reverse()`](../../apps/app_operation/models/operation.py:997) |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | [`models.py`](../../apps/app_transaction/models.py:33) |
| `PURCHASE_ISSUANCE` (project → vendor, non-cash) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:15), entity map [:497](../../apps/app_transaction/transaction_type.py:497), op map [:592](../../apps/app_transaction/transaction_type.py:592), issuance set [:450](../../apps/app_transaction/transaction_type.py:450) |
| `PURCHASE_PAYMENT` (project → vendor, affects balance) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:22), entity map [:498](../../apps/app_transaction/transaction_type.py:498), op map [:593](../../apps/app_transaction/transaction_type.py:593), payment set [:422](../../apps/app_transaction/transaction_type.py:422) |
| `PURCHASE_ADJUSTMENT_INCREASE` (project → vendor, non-cash) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:29), entity map [:499](../../apps/app_transaction/transaction_type.py:499), op map [:594](../../apps/app_transaction/transaction_type.py:594) |
| `PURCHASE_ADJUSTMENT_DECREASE` (vendor → project, non-cash) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:40), entity map [:500](../../apps/app_transaction/transaction_type.py:500), op map [:595](../../apps/app_transaction/transaction_type.py:595) |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Balance derivation | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) |
| Payables / receivables derivation (issuance + adjustment types) | [`payables_at`](../../apps/app_entity/models/__init__.py:476) / [`receivables_at`](../../apps/app_entity/models/__init__.py:511) |
| Balance check for real payer funds | [`Entity.can_pay`](../../apps/app_entity/models/__init__.py:704) |
| Open period auto-creation | [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Purchase wizard (create flow) | [`purchase_wizard_view`](../../apps/app_operation/views/create_operation/purchase_wizard.py:100), [`purchase_submit_view`](../../apps/app_operation/views/create_operation/purchase_wizard.py:482) |
| Factory: full create pipeline (items + movements + payment) | [`create_from_session`](../../apps/app_operation/models/proxies/op_purchase.py:105) |
| POST parsing/validation | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) |
| Reverse view | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) |
| Pay view (standalone) | [`record_transaction_payment`](../../apps/app_operation/views/record_transaction.py:17) |
| Adjust view (amount) / adjust items view | [`record_accounting_adjustment`](../../apps/app_operation/views/adjustment.py:37) / [`record_item_adjustment`](../../apps/app_operation/views/adjustment.py:135) |
| Move items view (detail-page / inventory shortcut) | [`create_inventory_movement`](../../apps/app_inventory/views.py:642) |
| Detail view | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) |
| URLs (wizard, payment, adjust, item-adjust, detail, reverse) | [`urls.py`](../../apps/app_operation/urls.py:53) |
| Templates | [`templates/app_operation/`](../../apps/app_operation/templates/app_operation/) — `purchase_wizard.html`, `purchase_form.html`, `purchase_invoice.html`, `purchase_add_item.html`, `purchase_select_template.html`, `add_payment_form.html`, `operation_detail.html`, `reverse_form.html` |

### 2.6 Tests

| Concern | Test file |
|---------|-----------|
| Create branches | [`test_purchase_create.py`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py) |
| Payment branches | [`test_purchase_payment.py`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py) |
| Reversal branches | [`test_purchase_reversal.py`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py) |
| Movement branches | [`test_inventory_movement.py`](../../apps/app_inventory/tests/test_inventory_movement.py) |
| Adjustment / adjust-items branches | [`apps/app_adjustment/tests/`](../../apps/app_adjustment/tests/) |
| Coverage manifest (executable branch registry) | [`tests/base.py`](../../apps/app_operation/tests/base.py:361) |

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

- **Payment source fund:** `self.source` (project) — [`op_purchase.py`](../../apps/app_operation/models/proxies/op_purchase.py:43)
- **Payment target fund:** `self.destination` (vendor) — [`op_purchase.py`](../../apps/app_operation/models/proxies/op_purchase.py:47)
- **Effect split:** the issuance tx records the obligation once (project payables ↑, vendor receivables ↑); fund balances move **only** on payment.

---

## 4. Settlement model

Derived from [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:242) using `PURCHASE_PAYMENT` transactions only. Because the operation is adjustable, `total_settlable_amount = effective_amount` (amount ± active adjustments).

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
| VC1 | Source is Project | `source.is_project` | `ValidationError` | `"Purchase source must be a Project entity."` | [`clean_source`](../../apps/app_operation/models/proxies/op_purchase.py:58) | [`test_source_must_be_a_project_entity`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:197) |
| VC2 | Destination is Vendor | `destination.is_vendor` | `ValidationError` | `"Purchase destination must be a Vendor entity."` | [`clean_destination`](../../apps/app_operation/models/proxies/op_purchase.py:77) | [`test_destination_must_be_a_vendor_entity`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:223) |
| VC3 | Destination not internal | `not destination.is_internal` | `ValidationError` | `"Internal entities cannot be vendors…"` | [`clean_destination`](../../apps/app_operation/models/proxies/op_purchase.py:82) | [`test_purchase_rejects_internal_vendor`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:459) |
| VC4 | Destination is an active vendor stakeholder of the source project | active `Stakeholder(parent=source, target=dest, role=VENDOR)` | `ValidationError` | `"Purchase destination must be an active vendor of the source project."` | [`clean_destination`](../../apps/app_operation/models/proxies/op_purchase.py:89) | [`test_destination_must_be_active_stakeholder_vendor`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:236), [`test_destination_with_inactive_stakeholder_raises_validation_error`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:243) |
| VC5 | Destination is not a Project | project is not a vendor | `ValidationError` | same as VC2 / VC3 | [`clean_destination`](../../apps/app_operation/models/proxies/op_purchase.py:77) | [`test_destination_project_entity_raises_validation_error`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:230) |
| VC6 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | [`test_source_must_be_active`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:203) |
| VC7 | Destination entity active | `destination.active` | `ValidationError` | same as VC6 | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | merged with VC4 (inactive vendor) |
| VC8 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | [`SourceFundMixin`](../../apps/app_base/mixins.py:132) | [`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:211) |
| VC9 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | [`TargetFundMixin`](../../apps/app_base/mixins.py:152) | merged with VC8 |
| VC10 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | [`AmountCleanMixin`](../../apps/app_base/mixins.py:69) | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:255), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:260) |
| VC11 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:81) | [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:269) |
| VC12 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:84) | [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:278) |
| VC13 | Date not in a closed period (source + destination) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:541) | covered by period suite |
| VC14 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) | covered by period suite |
| VC15 | Balance exempt @ create (issuance unguarded) | not one-shot; issuance is non-cash | never fails | — | `_is_one_shot_operation=False` | [`test_project_fund_balance_unchanged_after_save`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:141) |
| VC16 | Tx entity-type contract | `source.is_project` and `target.is_vendor` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | [`Transaction.create()`](../../apps/app_transaction/models.py:144) + map [:497](../../apps/app_transaction/transaction_type.py:497) | implied by VC1/VC2 |
| VC17 | Tx operation-type allowed | document is `PURCHASE` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | [`Transaction.create()`](../../apps/app_transaction/models.py:155) + map [:592](../../apps/app_transaction/transaction_type.py:592) | implied by VC1/VC2 |
| VC18 | Source ≠ target | project ≠ vendor | always true | `"Source and target funds must be different."` | [`Transaction.clean()`](../../apps/app_transaction/models.py:107) | structural (project ≠ vendor) |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | exactly 1 × `PURCHASE_ISSUANCE`, amount `== op.amount`, `project → vendor` | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:222) | [`test_save_creates_exactly_one_issuance_transaction`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:114) |
| SC2 | No payment tx on save | not one-shot → `LinkedPaymentTransactionMixin.save()` is a no-op | [`LinkedPaymentTransactionMixin.save()`](../../apps/app_base/mixins.py:424) | [`test_no_payment_transaction_created_on_save`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:120) |
| SC3 | Issuance direction | `tx.source=project.fund`, `tx.target=vendor.fund` | [`op_purchase.py`](../../apps/app_operation/models/proxies/op_purchase.py:43) | [`test_issuance_transaction_direction_is_project_to_vendor`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:126) |
| SC4 | Issuance amount matches | `tx.amount == op.amount` | transaction creation | [`test_issuance_transaction_amount_matches_operation`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:134) |
| SC5 | Issuance is non-cash | project fund balance unchanged after save | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) | [`test_project_fund_balance_unchanged_after_save`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:141) |
| SC6 | Remaining equals full amount | `amount_remaining_to_settle == amount` | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:301) | [`test_amount_remaining_to_settle_equals_full_amount_after_creation`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:151) |
| SC7 | Not fully settled | `is_fully_settled is False` | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:307) | [`test_is_not_fully_settled_after_creation`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:157) |
| SC8 | Project payables ▲ | `project.payables == amount` | [`payables_at`](../../apps/app_entity/models/__init__.py:476) | [`test_create_project_payables_increase`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:167) |
| SC9 | Vendor receivables ▲ | `vendor.receivables == amount` | [`receivables_at`](../../apps/app_entity/models/__init__.py:511) | [`test_create_vendor_receivables_increase`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:174) |
| SC10 | Project receivables unchanged | `project.receivables == 0` | [`receivables_at`](../../apps/app_entity/models/__init__.py:511) | [`test_create_project_receivables_unchanged`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:181) |
| SC11 | Vendor payables unchanged | `vendor.payables == 0` | [`payables_at`](../../apps/app_entity/models/__init__.py:476) | [`test_create_vendor_payables_unchanged`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:187) |
| SC12 | Invoice items created | one `InvoiceItem` per session item, linked to product template | [`create_from_session`](../../apps/app_operation/models/proxies/op_purchase.py:160) | [`test_create_from_session_basic`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:415) |
| SC13 | Ledger / pending obligation | purchased-but-unreceived item = pending inbound (no movement lines) | [`pending_items`](../../apps/app_inventory/stock.py:178) | [`test_create_from_session_ledger_entries_created`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:916) |
| SC14 | Period auto-assigned | `period` = covering period of the source project | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) | covered by period suite |

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:34) | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:239) |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:47) | [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:246) |
| VR3 | No non-reversed payment tx | no `PURCHASE_PAYMENT` exists (payments are explicit, not implicit) | `ValidationError` | `"You can't reverse this object as it has non-reversed transactions…"` | [`ReversableModel._requires_transaction_reversal`](../../apps/app_base/models.py:203) + [`Operation._implicit_reversable_transaction_types`](../../apps/app_operation/models/operation.py:479) | [`test_reversal_blocked_when_payment_exists`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:225) |
| VR4 | No non-reversed movement lines | all user-driven movements reversed first | `ValidationError` | `"Reverse all inventory movements first."` | [`Operation.reverse()`](../../apps/app_operation/models/operation.py:1056) | covered by inventory suite |
| VR5 | No non-reversed adjustments | all adjustments reversed first | `ValidationError` | `"You can't reverse this object as it has non-reversed adjustments…"` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:248) | covered by adjustment suite |
| VR6 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:82) | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:235) | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:113) |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:273) | [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:119) |
| SR3 | Reversal marked as `is_reversal` | `reversal.reversal_of == original`, not reversed | [`ReversableModel`](../../apps/app_base/models.py:149) | [`test_reversal_is_marked_as_reversal`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:126) |
| SR4 | Reversal inherits identity | `amount`, `source`, `destination` copied | [`ReversableModel._get_reverse_kwargs`](../../apps/app_base/models.py:184) | [`test_reverse_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:132) |
| SR5 | Counter-tx for issuance only | 1 original + 1 counter `PURCHASE_ISSUANCE`; payment blocks reversal | [`Operation._implicit_reversable_transaction_types`](../../apps/app_operation/models/operation.py:479) | [`test_reverse_creates_counter_transaction_for_issuance`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:139) |
| SR6 | Counter-tx flips funds | `counter.source == original.target`, `counter.target == original.source` | [`Transaction.reverse()`](../../apps/app_transaction/models.py:207) | [`test_reverse_counter_transaction_flips_funds`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:150) |
| SR7 | Project fund unchanged | issuance is non-cash; reversal leaves fund balance untouched | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) | [`test_project_fund_unchanged_after_reversal`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:160) |
| SR8 | Project payables restored | `project.payables` back to `0.00` | [`payables_at`](../../apps/app_entity/models/__init__.py:476) | [`test_reverse_restores_project_payables`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:174) |
| SR9 | Vendor receivables restored | `vendor.receivables` back to `0.00` | [`receivables_at`](../../apps/app_entity/models/__init__.py:511) | [`test_reverse_restores_vendor_receivables`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:181) |
| SR10 | Differential invariant | create + reverse leaves balances, payables, receivables and ledger unchanged | whole engine | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:202) |
| SR11 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:226) | implied by reversal tests |

### 5.3 `pay`

Standalone action — from the wizard (step 3, initial payment), later from the purchase detail page, or via [`record_transaction_payment`](../../apps/app_operation/views/record_transaction.py:17). Model entry points: `create_payment_transaction()` / `process_payment()`.

#### 5.3.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VP1 | Balance enforced per payment | `payment_source_fund.can_pay(amount)` | `ValidationError` | `"Insufficient funds: fund balance …"` | [`create_payment_transaction`](../../apps/app_base/mixins.py:377) | [`test_check_balance_on_payment_is_enabled`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:213), [`test_payment_blocked_when_project_fund_has_insufficient_balance`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:217) |
| VP2 | Amount > 0 | `amount > 0` | `ValidationError` | `"The amount should be more than 0"` | [`validate_settlement_amount`](../../apps/app_base/mixins.py:318) | [`test_zero_payment_raises_validation_error`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:201) |
| VP3 | Amount ≤ remaining (over-payment guard) | `amount <= amount_remaining_to_settle` | `ValidationError` | `"The paid amount … exceeds the remaining …"` | [`validate_settlement_amount`](../../apps/app_base/mixins.py:320) | [`test_payment_exceeding_operation_amount_raises_validation_error`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:191), [`test_partial_payment_then_over_payment_raises_validation_error`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:195) |
| VP4 | Negative blocked | `amount > 0` | `ValidationError` | same as VP2 | [`validate_settlement_amount`](../../apps/app_base/mixins.py:318) | [`test_negative_payment_raises_validation_error`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:205) |
| VP5 | Partial allowed — multiple payments | `max_payment_transaction_count == -1` | — | — | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:342) | [`test_multiple_partial_payments_are_allowed`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:135) |
| VP6 | Payment date not in a closed period | `period_entity` open on `date` | `ValidationError` | `"Cannot record a payment dated within a closed financial period."` | [`create_payment_transaction`](../../apps/app_base/mixins.py:370) | covered by period suite |

#### 5.3.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SP1 | Payment tx created | 1 × `PURCHASE_PAYMENT`, `project.fund → vendor.fund` | [`create_payment_transaction`](../../apps/app_base/mixins.py:410) | [`test_payment_creates_purchase_payment_transaction`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:115), [`test_payment_transaction_direction_is_project_to_vendor`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:123) |
| SP2 | Remaining decreases | `amount_remaining_to_settle` ↓ by payment | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:301) | [`test_amount_remaining_to_settle_decreases_after_payment`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:130) |
| SP3 | Settled accumulates | `amount_settled = Σ payments` | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:269) | [`test_multiple_payments_accumulate_correctly`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:146) |
| SP4 | Full payment → fully settled | `is_fully_settled`, remaining `0.00` | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:307) | [`test_full_payment_marks_operation_as_fully_settled`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:153) |
| SP5 | Project fund ▼ | `project.balance` decreases by payment (cash) | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) | [`test_project_fund_decreases_by_payment_amount`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:159) |
| SP6 | Vendor fund ▲ | `vendor.balance` increases by payment | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) | [`test_vendor_fund_increases_by_payment_amount`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:170) |
| SP7 | Tx count after partial pay | 1 issuance + 1 payment = 2 | — | [`test_total_transactions_after_partial_payment_is_two`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:181) |

### 5.4 `move items`

Receiving goods into project inventory — from the wizard (step 4), later from the purchase detail page, or from an inventory shortcut via [`create_inventory_movement`](../../apps/app_inventory/views.py:642). The wizard path uses [`create_from_session`](../../apps/app_operation/models/proxies/op_purchase.py:170).

#### 5.4.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VM1 | Operation not reversed; movements enabled | `creates_assets=True`; no active reversal | `ValidationError` | — | [`Operation.reverse()`](../../apps/app_operation/models/operation.py:1056) + stock layer | covered by inventory suite |
| VM2 | Qty ≤ item remaining qty | `received_qty ≤ adjusted_quantity − moved` | `ValidationError` | — | [`pending_items`](../../apps/app_inventory/stock.py:178) / [`active_lines_for_item`](../../apps/app_inventory/stock.py:51) | covered by inventory suite |
| VM3 | Product allowed + officer valid | product active/obligated; officer staff + active | `ValidationError` | — | [`InventoryMovementLine.save()`](../../apps/app_inventory/models.py:1202) | covered by inventory suite |

#### 5.4.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SM1 | Movement lines + ledger | `PURCHASE_MOVEMENT` ledger; `InventoryMovementLine` records | [`create_from_session`](../../apps/app_operation/models/proxies/op_purchase.py:170) | [`test_create_inventory_movement_purchase`](../../apps/app_inventory/tests/test_inventory_movement.py:59) |
| SM2 | INDIVIDUAL → one line per head | moving 10 animals creates 10 lines of qty 1 (one tagged Product each) | [`create_from_session`](../../apps/app_operation/models/proxies/op_purchase.py:176) | [`test_create_from_session_with_received_qty`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:548), [`test_create_from_session_partial_received_qty`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:598) |
| SM3 | COMMODITY → one line with full qty | moving 10 kg of corn creates one line qty 10 | [`create_from_session`](../../apps/app_operation/models/proxies/op_purchase.py:195) | covered by inventory suite |
| SM4 | Lazy product creation; remaining ↓ | products created by movement line `save()`; item remaining qty ↓ | [`InventoryMovementLine.save()`](../../apps/app_inventory/models.py:1202) | [`test_create_from_session_with_received_qty`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:583), [`test_create_from_session_ledger_entries_created`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:916) |
| SM5 | Movement reversible | reversed lines excluded from active stock | [`active_lines_for_item`](../../apps/app_inventory/stock.py:51) | covered by inventory suite |

### 5.5 `adjust items`

Invoice-item correction (qty / unit price) via [`record_item_adjustment`](../../apps/app_operation/views/adjustment.py:135). This is the sanctioned way to change the purchase issuance amount.

#### 5.5.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VA1 | Adjustable + not reversed / not a reversal | `is_items_adjustable=True`; no active reversal | `ValidationError` | — | [`InvoiceItemAdjustment`](../../apps/app_adjustment/models.py) | covered by adjustment suite |
| VA2 | ≥ 1 item changed; qty/price parse | at least one delta, valid decimal | `ValidationError` | — | item-adjustment finalize | covered by adjustment suite |
| VA3 | New qty ≥ already moved | `new_qty ≥ moved_qty` | `ValidationError` | — | item-adjustment finalize | covered by adjustment suite |

#### 5.5.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SA1 | Item adjustment + lines | `InvoiceItemAdjustment` + lines; item adjusted qty/price | [`record_item_adjustment`](../../apps/app_operation/views/adjustment.py:135) | covered by adjustment suite |
| SA2 | Accounting `Adjustment` + tx | `*_ADJUSTMENT` transaction (non-cash) | [`record_item_adjustment`](../../apps/app_operation/views/adjustment.py:135) | covered by adjustment suite |
| SA3 | Inventory ledger entries | `*_ADJUSTMENT` ledger entries | [`InvoiceItemAdjustment.finalize()`](../../apps/app_adjustment/models.py) | [`test_purchase_price_decrease_ledger_entry`](../../apps/app_adjustment/tests/test_invoice_item_adjustment_ledger_entry.py:178) |

### 5.6 `adjust`

Accounting adjustment on the operation amount via [`record_accounting_adjustment`](../../apps/app_operation/views/adjustment.py:37). Adjusting changes `effective_amount` → the total purchase amount, project payables and vendor receivables all change accordingly.

#### 5.6.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VA4 | Adjustable + not reversed / not a reversal | `is_adjustable=True`; no active reversal | `ValidationError` | — | [`Adjustment`](../../apps/app_adjustment/models.py) | covered by adjustment suite |
| VA5 | Adjustment type allowed for PURCHASE | `PURCHASE_RETURN` etc → `PURCHASE_ADJUSTMENT_INCREASE` / `PURCHASE_ADJUSTMENT_DECREASE` | `ValidationError` | — | adjustment type map | covered by adjustment suite |
| VA6 | Amount > 0; officer staff + active | valid amount + officer | `ValidationError` | — | [`Adjustment`](../../apps/app_adjustment/models.py) | covered by adjustment suite |
| VA7 | Reduction can't drive below zero | `effective_amount ≥ 0` after reduction | `ValidationError` | — | [`Adjustment`](../../apps/app_adjustment/models.py) | covered by adjustment suite |

#### 5.6.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SA4 | Adjustment tx (non-cash) + `effective_amount` delta | `PURCHASE_ADJUSTMENT_INCREASE` / `PURCHASE_ADJUSTMENT_DECREASE`; payables/receivables reflect delta | [`record_accounting_adjustment`](../../apps/app_operation/views/adjustment.py:37) + [`AdjustableMixin.effective_amount`](../../apps/app_base/mixins.py:96) | [`test_single_decrease_reduces_effective_amount`](../../apps/app_adjustment/tests/test_adjustment_adjustment_effective_amount.py:192), [`test_purchase_return_reduces_project_payables`](../../apps/app_adjustment/tests/test_adjustment_adjustment_reversal.py:252) |

### 5.7 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by [`ImmutableMixin`](../../apps/app_base/mixins.py:30) via `_immutable_fields` ([`operation.py`](../../apps/app_operation/models/operation.py:51)).

| Branch | Enforced by | Pinned by test |
|--------|-------------|----------------|
| `source` changed after save | `ImmutableMixin.save()` | [`test_source_is_immutable_after_save`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:290) |
| `destination` changed after save | `ImmutableMixin.save()` | [`test_destination_is_immutable_after_save`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:986) |
| `amount` changed after save | `ImmutableMixin.save()` | [`test_amount_is_immutable_after_save`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:996) |

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — [`Entity.save()`](../../apps/app_entity/models/__init__.py:714).
- The operation's governing entity (`period_entity`) is the **source project** (`_source_role = "url"`) — [`Operation.period_entity`](../../apps/app_operation/models/operation.py:492).
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC14).
- New operations dated inside a **closed** period are rejected (VC13) — [`is_date_in_closed_period`](../../apps/app_operation/models/period.py:14).
- **Payments** dated inside a closed period of the governing entity are rejected (VP6) — [`create_payment_transaction`](../../apps/app_base/mixins.py:370).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period ([`_reverse_period`](../../apps/app_operation/models/operation.py:455)).

---

## 7. Entity roles & balance contract

- **Source:** must be a Project — enforced at model (VC1 [`clean_source`](../../apps/app_operation/models/proxies/op_purchase.py:58)) and transaction (VC16 [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:497)) layers.
- **Destination:** must be an external Vendor that is an **active vendor stakeholder** of the source project — enforced at model (VC2/VC3/VC4 [`clean_destination`](../../apps/app_operation/models/proxies/op_purchase.py:77)) and transaction (VC16) layers. Internal entities are never vendors (VC3); intra-farm transfers go through SALE.
- `project.payables` and `vendor.receivables` are derived from **issuance + adjustment** types (non-cash) — [`payables_at`](../../apps/app_entity/models/__init__.py:476) / [`receivables_at`](../../apps/app_entity/models/__init__.py:511).
- `project.balance` and `vendor.balance` are derived exclusively from **payment-type** transactions — [`balance_at`](../../apps/app_entity/models/__init__.py:414).
- The project fund is a **real** fund, so `can_pay()` balance-checks it; `check_balance_on_payment=True` guards each payment (VP1). Issuance itself is unguarded (VC15).

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Create route | Wizard `GET/POST /<project_pk>/purchase/wizard/` (+ `/…/<step>/`, `/cancel/`) → [`purchase_wizard_view`](../../apps/app_operation/views/create_operation/purchase_wizard.py:100); submit → [`purchase_submit_view`](../../apps/app_operation/views/create_operation/purchase_wizard.py:482) (URLs [`urls.py`](../../apps/app_operation/urls.py:53)) |
| Source selection | locked to the **Project** from the URL (`_source_role="url"`); no picker |
| Destination selection | active **vendor stakeholders** of the project, **excluding internal entities** ([`get_related_entities`](../../apps/app_operation/models/proxies/op_purchase.py:63)); picker + product templates restricted to the project |
| Category | hidden (no category) |
| Amount | derived from invoice-item totals — wizard computes `total_amount`, validated by [`_validate_item_totals`](../../apps/app_operation/models/proxies/op_purchase.py:145); user **cannot** manually edit the amount |
| POST parsing | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) |
| Initial payment | wizard step 3 — `amount_paid` (0 allowed); goes through `create_payment_transaction` |
| Record payment (later) | detail-page "Record Payment" → [`record_transaction_payment`](../../apps/app_operation/views/record_transaction.py:17) (URL [`urls.py`](../../apps/app_operation/urls.py:153)); template [`add_payment_form.html`](../../apps/app_operation/templates/app_operation/add_payment_form.html) |
| Move items | wizard step 4, detail-page shortcut, or inventory shortcut → [`create_inventory_movement`](../../apps/app_inventory/views.py:642) |
| Adjust / adjust items | [`record_accounting_adjustment`](../../apps/app_operation/views/adjustment.py:37) / [`record_item_adjustment`](../../apps/app_operation/views/adjustment.py:135) (URLs [`urls.py`](../../apps/app_operation/urls.py:158), [`:163`](../../apps/app_operation/urls.py:163)) |
| Detail | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) — total amount, paid so far, remaining; movement status; "Record Payment", adjust, and reversal actions |
| Reverse | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

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
| Issuance tx count | [`test_save_creates_exactly_one_issuance_transaction`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:114), [`test_no_payment_transaction_created_on_save`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:120) | SC1, SC2 |
| Issuance direction + amount | [`test_issuance_transaction_direction_is_project_to_vendor`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:126), [`test_issuance_transaction_amount_matches_operation`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:134) | SC3, SC4 |
| Issuance non-cash | [`test_project_fund_balance_unchanged_after_save`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:141) | SC5, VC15 |
| Settlement after create | [`test_amount_remaining_to_settle_equals_full_amount_after_creation`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:151), [`test_is_not_fully_settled_after_creation`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:157) | SC6, SC7 |
| Payables / receivables | [`test_create_project_payables_increase`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:167), [`test_create_vendor_receivables_increase`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:174), [`test_create_project_receivables_unchanged`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:181), [`test_create_vendor_payables_unchanged`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:187) | SC8–SC11 |
| Source validation | [`test_source_must_be_a_project_entity`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:197), [`test_source_must_be_active`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:203), [`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:211) | VC1, VC6, VC8 |
| Destination validation | [`test_destination_must_be_a_vendor_entity`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:223), [`test_destination_project_entity_raises_validation_error`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:230), [`test_destination_must_be_active_stakeholder_vendor`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:236), [`test_destination_with_inactive_stakeholder_raises_validation_error`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:243) | VC2, VC5, VC4, VC7 |
| Internal-vendor guard | [`test_purchase_rejects_internal_vendor`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:459), [`test_get_related_entities_excludes_internal_vendors`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:485) | VC3 |
| Amount / officer | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:255), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:260), [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:269), [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:278) | VC10–VC12 |
| Immutability | [`test_source_is_immutable_after_save`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:290), [`test_destination_is_immutable_after_save`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:986), [`test_amount_is_immutable_after_save`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:996) | IM1–IM3 |
| Wizard basic flow | [`test_create_from_session_basic`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:415), [`test_create_from_session_creates_issuance_transaction`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:524) | SC12, SC1, SC3 |
| Wizard movements | [`test_create_from_session_with_received_qty`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:548), [`test_create_from_session_partial_received_qty`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:598), [`test_create_from_session_full_flow`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:713) | SM2, SM4 |
| Wizard payment | [`test_create_from_session_with_payment`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:629), [`test_create_from_session_full_payment`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:690), [`test_create_from_session_zero_payment`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:672) | SP1–SP6 |
| Wizard integrity | [`test_create_from_session_item_totals_mismatch`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:776), [`test_create_from_session_payment_exceeds_total`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:859), [`test_create_from_session_missing_vendor_raises_error`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:838) | amount-source contract |
| Ledger / pending | [`test_create_from_session_ledger_entries_created`](../../apps/app_operation/tests/operations/purchase/test_purchase_create.py:916) | SC13, SM4 |
| Payment happy path | [`test_payment_creates_purchase_payment_transaction`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:115), [`test_payment_transaction_direction_is_project_to_vendor`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:123) | SP1 |
| Payment settlement | [`test_amount_remaining_to_settle_decreases_after_payment`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:130), [`test_multiple_partial_payments_are_allowed`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:135), [`test_multiple_payments_accumulate_correctly`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:146), [`test_full_payment_marks_operation_as_fully_settled`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:153) | SP2–SP4, VP5 |
| Payment fund movement | [`test_project_fund_decreases_by_payment_amount`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:159), [`test_vendor_fund_increases_by_payment_amount`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:170) | SP5, SP6 |
| Over-payment / zero / negative | [`test_payment_exceeding_operation_amount_raises_validation_error`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:191), [`test_partial_payment_then_over_payment_raises_validation_error`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:195), [`test_zero_payment_raises_validation_error`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:201), [`test_negative_payment_raises_validation_error`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:205) | VP2, VP3, VP4 |
| Balance on payment | [`test_check_balance_on_payment_is_enabled`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:213), [`test_payment_blocked_when_project_fund_has_insufficient_balance`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:217) | VP1 |
| Tx count | [`test_total_transactions_after_partial_payment_is_two`](../../apps/app_operation/tests/operations/purchase/test_purchase_payment.py:181) | SP7 |
| Reverse happy path | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:113), [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:119), [`test_reversal_is_marked_as_reversal`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:126), [`test_reverse_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:132) | SR1–SR4 |
| Reverse counter-tx | [`test_reverse_creates_counter_transaction_for_issuance`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:139), [`test_reverse_counter_transaction_flips_funds`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:150) | SR5, SR6 |
| Reverse balances/payables | [`test_project_fund_unchanged_after_reversal`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:160), [`test_reverse_restores_project_payables`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:174), [`test_reverse_restores_vendor_receivables`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:181), [`test_reverse_project_receivables_unchanged`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:188), [`test_reverse_vendor_payables_unchanged`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:193) | SR7–SR9 |
| Reverse constraints | [`test_reversal_blocked_when_payment_exists`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:225), [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:239), [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:246) | VR1, VR2, VR3 |
| Differential invariant | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/purchase/test_purchase_reversal.py:202) | SR10 |
| Movement (purchase) | [`test_create_inventory_movement_purchase`](../../apps/app_inventory/tests/test_inventory_movement.py:59) | SM1–SM5, VM1–VM3 |
| Adjust items — ledger | [`test_purchase_price_decrease_ledger_entry`](../../apps/app_adjustment/tests/test_invoice_item_adjustment_ledger_entry.py:178) | SA3 |
| Adjust — effective amount | [`test_single_decrease_reduces_effective_amount`](../../apps/app_adjustment/tests/test_adjustment_adjustment_effective_amount.py:192) | SA4 |
| Adjust — payables / reverse | [`test_purchase_return_reduces_project_payables`](../../apps/app_adjustment/tests/test_adjustment_adjustment_reversal.py:252), [`test_reverse_adjustment_restores_project_payables`](../../apps/app_adjustment/tests/test_adjustment_adjustment_reversal.py:261) | SA4, VR5 |

---

## 11. Tasks

- [x] Verify save creates only one PURCHASE_ISSUANCE transaction (not payment — not one-shot)
- [x] Verify no PURCHASE_PAYMENT transaction is created on save
- [x] Verify PURCHASE_ISSUANCE direction: source=project.fund, target=vendor.fund
- [x] Verify PURCHASE_ISSUANCE is non-cash: project fund balance unchanged after save
- [x] Verify amount_remaining_to_settle equals full amount after creation
- [x] Verify is_not_fully_settled after creation
- [x] Verify source must be a Project entity (non-project source raises ValidationError)
- [x] Verify source must be active (inactive source raises ValidationError)
- [x] Verify source fund must be active
- [x] Verify destination must be a Vendor entity (non-vendor destination raises ValidationError)
- [x] Verify project entity as destination raises ValidationError
- [x] Verify destination must be an active vendor stakeholder (non-stakeholder raises ValidationError)
- [x] Verify destination with inactive stakeholder raises ValidationError
- [x] Verify internal entity cannot be a vendor (internal-vendor guard)
- [x] Verify amount/officer validations (zero, negative, non-staff, inactive)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify payment creates PURCHASE_PAYMENT transaction (direction: project.fund → vendor.fund)
- [x] Verify payment amount_remaining_to_settle decreases correctly
- [x] Verify multiple partial payments are allowed and accumulate
- [x] Verify full payment marks operation as fully settled
- [x] Verify project fund decreases by payment amount (PURCHASE_PAYMENT is cash)
- [x] Verify vendor fund increases by payment amount
- [x] Verify payment cannot exceed remaining amount (over-payment raises ValidationError)
- [x] Verify partial then over-payment raises ValidationError
- [x] Verify zero/negative payment raises ValidationError
- [x] Verify balance enforced on payment (insufficient project fund raises ValidationError)
- [x] Reversal creates reversal operation with correct linkage
- [x] Verify reversal marks original as reversed
- [x] Verify reversal is marked as is_reversal
- [x] Verify reversal inherits amount, source, destination from original
- [x] Verify reversal creates counter-transaction for issuance only
- [x] Verify reversal counter-transaction flips source/target funds
- [x] Verify project fund unchanged after reversal (issuance is non-cash)
- [x] Verify payables/receivables restored after reversal (project payables, vendor receivables)
- [x] Verify reversal is blocked when any PURCHASE_PAYMENT transaction exists
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [x] Verify create + reverse differential invariant (balances/payables/receivables/ledger unchanged)
- [x] Verify movement lines: INDIVIDUAL → one line per head; COMMODITY → one line full qty
- [x] Verify lazy product creation and remaining-qty accounting on move items
- [x] Verify movement lines are reversible
- [ ] Pin movement reversal guard (VR4: reverse blocked while non-reversed movement lines exist) with a focused purchase test
- [ ] Pin closed-period payment guard (VP6) with a focused purchase test
- [ ] Add FK from Operation to FinancialCategory to enforce category_required at model save level (n/a for purchase — `has_category=False`)
- [ ] UI: create form — source=Project (url entity), destination=Vendor (from stakeholders), optional invoice formset
- [ ] UI: detail shows total amount, paid so far, remaining; "Record Payment" button
- [ ] Complete test coverage matrix §10 for every branch (mark tasks `[x]` once pinned)
