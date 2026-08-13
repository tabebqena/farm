# Sale — Operation Contract

**Epic:** 11.2 — Payable Operations
**Type:** Multi-stage — non-one-shot, partially payable, invoice-based (receivable + inventory)
**Actions:** `create`, `pay` (collection), `move items`, `adjust items`, `adjust`, `reverse`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Sale** operation.
> Every clause below is registered to its implementing code (model → mixin → transaction → view) and to its pinning test.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> See [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md) for the shared structure and
> [`op_1_cash_injection.md`](op_1_cash_injection.md) for a fully worked example.

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.SALE` (`"SALE"`) | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:14) |
| Proxy class | `SaleOperation` | [`op_sale.py`](../../apps/app_operation/models/proxies/op_sale.py:13) |
| URL slug | `"sale"` | [`op_sale.py`](../../apps/app_operation/models/proxies/op_sale.py:17) |
| Label | `"Sale Issuance"` | [`op_sale.py`](../../apps/app_operation/models/proxies/op_sale.py:18) |
| Theme | n/a — not defined on proxy (defaults) | [`op_sale.py`](../../apps/app_operation/models/proxies/op_sale.py:13) |
| Source role | `post` (a Client entity, selected) | [`op_sale.py`](../../apps/app_operation/models/proxies/op_sale.py:19) |
| Destination role | `url` (a Project entity) | [`op_sale.py`](../../apps/app_operation/models/proxies/op_sale.py:20) |
| Registered in | `PROXY_MAP` | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:36) |
| Cross-op reference | row SA | [`operations-comparison.md`](operations-comparison.md:221) |

**Configuration flags** (all on [`op_sale.py`](../../apps/app_operation/models/proxies/op_sale.py:13)):

| Flag | Value | Meaning |
|------|-------|---------|
| `_issuance_transaction_type` | `SALE_ISSUANCE` | receivable tx created on save (non-cash) |
| `_payment_transaction_type` | `SALE_COLLECTION` | cash tx created per collection |
| `_is_one_shot_operation` | `False` | no payment fires at create; standalone collection action |
| `can_pay` | `True` | `process_payment()` is active |
| `is_partially_payable` | `True` | collections can be any fraction of the amount |
| `max_payment_transaction_count` | `-1` | unlimited partial collections |
| `check_balance_on_payment` | `True` | each collection is balance-checked against the client fund (internal clients) |
| `has_category` / `category_required` | `False` | no financial category |
| `has_repayment` | `False` | no repayment action |
| `has_invoice` | `True` | invoice items + inventory movements |
| `is_adjustable` / `is_items_adjustable` | `True` / `True` | amount + invoice-item adjustments allowed |
| `category_type` | `"SALE"` | category namespace (unused while `has_category=False`) |

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row links the clause to the code that must honor it.

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_source`/`clean_destination` + `create_from_session` | [`op_sale.py`](../../apps/app_operation/models/proxies/op_sale.py:13) |
| Proxy registry / URL→class resolution | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:36) |
| Shared `Operation` engine (`clean`, `save`, `reverse`, `process_payment`, period assignment, reversable tx types) | [`operation.py`](../../apps/app_operation/models/operation.py:34) |
| Operation type enum | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:14) |

### 2.2 Core engine (mixins / base)

| Concern | Implementing code |
|---------|-------------------|
| Immutability of `source`/`destination`/`amount`/`period` | [`ImmutableMixin`](../../apps/app_base/mixins.py:30) + `_immutable_fields` in [`operation.py`](../../apps/app_operation/models/operation.py:51) |
| Amount must be > 0 | [`AmountCleanMixin`](../../apps/app_base/mixins.py:64) |
| Officer must be staff + active | [`OfficerMixin`](../../apps/app_base/mixins.py:80) |
| Source fund exists + active | [`SourceFundMixin`](../../apps/app_base/mixins.py:127) |
| Target fund exists + active | [`TargetFundMixin`](../../apps/app_base/mixins.py:147) |
| Issuance tx creation on save (skipped for reversals) | [`LinkedIssuanceTransactionMixin`](../../apps/app_base/mixins.py:184) |
| Collection / settlement (`amount_settled`, `remaining`, `is_fully_settled`, balance check, over-collection guard) | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:242) |
| Repayment | n/a — `has_repayment=False` |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | [`ReversableModel`](../../apps/app_base/models.py:133) + [`Operation.reverse()`](../../apps/app_operation/models/operation.py:997) |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | [`models.py`](../../apps/app_transaction/models.py:33) |
| `SALE_ISSUANCE` (client → project, non-cash receivable) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:50), entity map [:502](../../apps/app_transaction/transaction_type.py:502), op map [:596](../../apps/app_transaction/transaction_type.py:596), issuance set [:453](../../apps/app_transaction/transaction_type.py:453) |
| `SALE_COLLECTION` (client → project, affects balance) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:57), entity map [:503](../../apps/app_transaction/transaction_type.py:503), op map [:597](../../apps/app_transaction/transaction_type.py:597), payment set [:423](../../apps/app_transaction/transaction_type.py:423) |
| `SALE_ADJUSTMENT_INCREASE` (client → project, non-cash) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:64), entity map [:504](../../apps/app_transaction/transaction_type.py:504), op map [:598](../../apps/app_transaction/transaction_type.py:598) |
| `SALE_ADJUSTMENT_DECREASE` (project → client, non-cash) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:70), entity map [:505](../../apps/app_transaction/transaction_type.py:505), op map [:599](../../apps/app_transaction/transaction_type.py:599) |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Balance derivation | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) |
| Payables / receivables derivation (issuance + adjustment types) | [`payables_at`](../../apps/app_entity/models/__init__.py:476) / [`receivables_at`](../../apps/app_entity/models/__init__.py:511) |
| Balance check for internal payer funds (external clients exempt) | [`Entity.can_pay`](../../apps/app_entity/models/__init__.py:704) |
| Open period auto-creation | [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Sale wizard (create flow — steps 1–3, session-only) | [`sale_wizard_view`](../../apps/app_operation/views/create_operation/sale_wizard.py:113) |
| Invoice / product selection / item add-edit-delete / submit | [`sale_invoice_view`](../../apps/app_operation/views/create_operation/sale_wizard.py:280), [`sale_select_product_view`](../../apps/app_operation/views/create_operation/sale_wizard.py:341), [`sale_add_item_view`](../../apps/app_operation/views/create_operation/sale_wizard.py:390), [`sale_delete_item_view`](../../apps/app_operation/views/create_operation/sale_wizard.py:486), [`sale_submit_view`](../../apps/app_operation/views/create_operation/sale_wizard.py:506) |
| Factory: full create pipeline (items + movements + optional collection) | [`create_from_session`](../../apps/app_operation/models/proxies/op_sale.py:98) |
| Generic create view redirects SALE to the wizard | [`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:131) |
| POST parsing/validation | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) |
| Reverse view | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) |
| Record collection view (standalone) | [`record_transaction_payment`](../../apps/app_operation/views/record_transaction.py:17) |
| Adjust view (amount) / adjust items view | [`record_accounting_adjustment`](../../apps/app_operation/views/adjustment.py:37) / [`record_item_adjustment`](../../apps/app_operation/views/adjustment.py:135) |
| Move items (detail-page / inventory shortcut) | [`create_inventory_movement`](../../apps/app_inventory/views.py:642) |
| Detail view | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) |
| URLs (wizard, invoice, item, collection, adjust, detail, reverse) | [`urls.py`](../../apps/app_operation/urls.py:97) |
| Templates | [`templates/app_operation/`](../../apps/app_operation/templates/app_operation/) — `sale_wizard.html`, `sale_invoice.html`, `sale_select_product.html`, `sale_add_item.html`, `add_payment_form.html`, `operation_detail.html`, `reverse_form.html` |

### 2.6 Tests

| Concern | Test file |
|---------|-----------|
| Create branches | [`test_sale_sale_create.py`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py) |
| Collection branches | [`test_sale_sale_collection.py`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py) |
| Collection balance guard (internal vs external client) | [`test_sale_sale_balance_guard.py`](../../apps/app_operation/tests/operations/sale/test_sale_sale_balance_guard.py) |
| Reversal branches | [`test_sale_sale_reversal.py`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py) |
| Wizard / movement / internal-client branches | [`test_sale_sale_create_from_session.py`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py) |
| Movement branches | [`test_inventory_movement.py`](../../apps/app_inventory/tests/test_inventory_movement.py) |
| Adjustment / adjust-items branches | [`apps/app_adjustment/tests/`](../../apps/app_adjustment/tests/) |
| Coverage manifest (executable branch registry) | [`tests/base.py`](../../apps/app_operation/tests/base.py:414) |

---

## 3. Money flow & entities

- **Source (payer):** a **Client** entity (`source.is_client=True`). It must be an **active client stakeholder** of the destination project (`Stakeholder(parent=project, target=client, role=CLIENT, active=True)`). Its fund is the payer fund; `check_balance_on_payment=True` means an **internal** client's fund must have enough balance at each collection (external clients are exempt — VC6 §7).
- **Destination (receiver):** a **Project** entity (`destination.is_project=True`). Its fund is the target fund.
- **Transaction flow:**

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `SALE_ISSUANCE` | `client.fund → project.fund` | none (issuance, non-cash receivable) |
| 2 | `SALE_COLLECTION` (0..n) | `client.fund → project.fund` | ▼ client fund, ▲ project fund by collection amount |
| 3 | `SALE_ADJUSTMENT_INCREASE` | `client.fund → project.fund` | none (non-cash; raises client payable) |
| 4 | `SALE_ADJUSTMENT_DECREASE` | `project.fund → client.fund` | none (non-cash; lowers client payable) |

- **Payment source fund:** `self.source` (client) — [`op_sale.py`](../../apps/app_operation/models/proxies/op_sale.py:43)
- **Payment target fund:** `self.destination` (project) — [`op_sale.py`](../../apps/app_operation/models/proxies/op_sale.py:47)
- **Effect split:** the issuance tx records the receivable once (project receivables ↑, client payables ↑); fund balances move **only** on collection.

---

## 4. Settlement model

Derived from [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:242) using `SALE_COLLECTION` transactions only. Because the operation is adjustable, `total_settlable_amount = effective_amount` (amount ± active adjustments).

| Property | After create | After partial collection | After full collection | After reverse |
|----------|--------------|--------------------------|-----------------------|---------------|
| `amount_settled` | `0.00` | `Σ collections` | `== effective_amount` | `0.00` |
| `total_settlable_amount` (`effective_amount`) | `== amount` | unchanged | unchanged | unchanged |
| `amount_remaining_to_settle` | `== amount` | `amount − Σ collections` | `0.00` | `== amount` |
| `is_fully_settled` | `False` | `False` | `True` | `False` |

Collections are **multi-stage**: the sale is created as a pure receivable; the client then pays the project in one or more installments up to the (adjusted) total.

---

## 5. Actions

### 5.1 `create`

Entry points: model `SaleOperation.save()` (tests) or the wizard → `SaleOperation.create_from_session()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx only — not one-shot).

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source is Client | `source.is_client` | `ValidationError` | `"Sale source must be a Client entity."` | [`clean_source`](../../apps/app_operation/models/proxies/op_sale.py:60) | [`test_source_must_be_a_client_entity`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:224), [`test_source_project_entity_raises_validation_error`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:230) |
| VC2 | Source is an active client stakeholder of the destination project | active `Stakeholder(parent=destination, target=source, role=CLIENT)` | `ValidationError` | `"Sale source must be an active client of the destination project."` | [`clean_source`](../../apps/app_operation/models/proxies/op_sale.py:65) | [`test_destination_must_be_active_stakeholder_project`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:262), [`test_destination_with_inactive_stakeholder_raises_validation_error`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:269) |
| VC3 | Destination is Project | `destination.is_project` | `ValidationError` | `"Sale destination must be a Project entity."` | [`clean_destination`](../../apps/app_operation/models/proxies/op_sale.py:88) | [`test_destination_must_be_a_project_entity`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:256) |
| VC4 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | [`test_source_must_be_active`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:236) |
| VC5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | [`SourceFundMixin`](../../apps/app_base/mixins.py:132) | [`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:244) |
| VC6 | Destination entity active | `destination.active` | `ValidationError` | same as VC4 | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | merged with VC2 (inactive stakeholder) |
| VC7 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | [`TargetFundMixin`](../../apps/app_base/mixins.py:152) | merged with VC6 |
| VC8 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | [`AmountCleanMixin`](../../apps/app_base/mixins.py:69) | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:281), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:286) |
| VC9 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:81) | [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:295) |
| VC10 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:84) | [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:303) |
| VC11 | Date not in a closed period (source + destination) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:541) | covered by period suite |
| VC12 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) | covered by period suite |
| VC13 | Balance exempt @ create (issuance unguarded) | not one-shot; issuance is non-cash | never fails | — | `_is_one_shot_operation=False` | [`test_project_fund_balance_unchanged_after_save`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:158), [`test_client_fund_balance_unchanged_after_save`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:168) |
| VC14 | Tx entity-type contract | `source.is_client` and `target.is_project` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | [`Transaction.create()`](../../apps/app_transaction/models.py:144) + map [:502](../../apps/app_transaction/transaction_type.py:502) | implied by VC1/VC2/VC3 |
| VC15 | Tx operation-type allowed | document is `SALE` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | [`Transaction.create()`](../../apps/app_transaction/models.py:155) + map [:596](../../apps/app_transaction/transaction_type.py:596) | implied by VC1/VC2/VC3 |
| VC16 | Source ≠ target | client ≠ project | always true | `"Source and target funds must be different."` | [`Transaction.clean()`](../../apps/app_transaction/models.py:107) | structural (client ≠ project) |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | exactly 1 × `SALE_ISSUANCE`, amount `== op.amount`, `client → project` | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:222) | [`test_save_creates_exactly_one_issuance_transaction`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:131) |
| SC2 | No collection tx on save | not one-shot → `LinkedPaymentTransactionMixin.save()` is a no-op | [`LinkedPaymentTransactionMixin.save()`](../../apps/app_base/mixins.py:424) | [`test_no_collection_transaction_created_on_save`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:137) |
| SC3 | Issuance direction | `tx.source=client.fund`, `tx.target=project.fund` | [`op_sale.py`](../../apps/app_operation/models/proxies/op_sale.py:43) | [`test_issuance_transaction_direction_is_client_to_project`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:143) |
| SC4 | Issuance amount matches | `tx.amount == op.amount` | transaction creation | [`test_issuance_transaction_amount_matches_operation`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:151) |
| SC5 | Issuance is non-cash | project fund balance unchanged after save | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) | [`test_project_fund_balance_unchanged_after_save`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:158) |
| SC6 | Client fund unchanged | `SALE_ISSUANCE` does not move client balance | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) | [`test_client_fund_balance_unchanged_after_save`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:168) |
| SC7 | Remaining equals full amount | `amount_remaining_to_settle == amount` | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:301) | [`test_amount_remaining_to_settle_equals_full_amount_after_creation`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:178) |
| SC8 | Not fully settled | `is_fully_settled is False` | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:307) | [`test_is_not_fully_settled_after_creation`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:184) |
| SC9 | Project receivables ▲ | `project.receivables == amount` | [`receivables_at`](../../apps/app_entity/models/__init__.py:511) | [`test_create_project_receivables_increase`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:194) |
| SC10 | Client payables ▲ | `client.payables == amount` | [`payables_at`](../../apps/app_entity/models/__init__.py:476) | [`test_create_client_payables_increase`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:201) |
| SC11 | Project payables unchanged | `project.payables == 0` | [`payables_at`](../../apps/app_entity/models/__init__.py:476) | [`test_create_project_payables_unchanged`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:208) |
| SC12 | Client receivables unchanged | `client.receivables == 0` | [`receivables_at`](../../apps/app_entity/models/__init__.py:511) | [`test_create_client_receivables_unchanged`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:214) |
| SC13 | Product linked; `SOLD` status is **movement-driven** | the issuance only records the receivable + invoice-item linkage — it does **not** mark the product. The product is marked `SOLD` by the `SALE_MOVEMENT` line at movement time (`net presence ≤ 0` with a terminal outbound SALE movement → `SOLD`); a partial dispatch keeps `ACTIVE`. (No-movement fallback: a registered-but-unmoved product linked to a non-reversed SALE item reports `SOLD` via linked-operation status only.) | [`Product.status`](../../apps/app_inventory/models.py:614) via [`create_from_session`](../../apps/app_operation/models/proxies/op_sale.py:204) | [`test_sale_full_disposal_leaves_zero`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:147), [`test_sale_individual_animal_affected`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:161), [`test_sale_affects_existing_product_no_mint`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:118) |
| SC14 | Internal client receives an ACTIVE clone | when `client.is_internal`, the buyer gets a clone (ACTIVE) + inbound receipt movement; seller's copy keeps remaining presence | [`create_from_session`](../../apps/app_operation/models/proxies/op_sale.py:221) | [`test_internal_client_receives_active_product`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:248) |
| SC15 | External client gets no buyer copy | no new product row for an external buyer | [`create_from_session`](../../apps/app_operation/models/proxies/op_sale.py:221) | [`test_external_client_gets_no_buyer_copy`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:285) |
| SC16 | Period auto-assigned | `period` = covering period of the destination project | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) | covered by period suite |

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:34) | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:260) |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:47) | [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:267) |
| VR3 | No non-reversed collection tx | no `SALE_COLLECTION` exists (collections are explicit, not implicit) | `ValidationError` | `"You can't reverse this object as it has non-reversed transactions…"` | [`ReversableModel._requires_transaction_reversal`](../../apps/app_base/models.py:203) + [`Operation._implicit_reversable_transaction_types`](../../apps/app_operation/models/operation.py:479) | [`test_reversal_blocked_when_collection_exists`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:246) |
| VR4 | No non-reversed movement lines | all user-driven movements reversed first | `ValidationError` | `"Reverse all inventory movements first."` | [`Operation.reverse()`](../../apps/app_operation/models/operation.py:1056) | covered by inventory suite |
| VR5 | No non-reversed adjustments | all adjustments reversed first | `ValidationError` | `"You can't reverse this object as it has non-reversed adjustments…"` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:248) | covered by adjustment suite |
| VR6 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:82) | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:235) | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:131) |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:273) | [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:137) |
| SR3 | Reversal marked as `is_reversal` | `reversal.reversal_of == original`, not reversed | [`ReversableModel`](../../apps/app_base/models.py:149) | [`test_reversal_is_marked_as_reversal`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:144) |
| SR4 | Reversal inherits identity | `amount`, `source`, `destination` copied | [`ReversableModel._get_reverse_kwargs`](../../apps/app_base/models.py:184) | [`test_reverse_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:150) |
| SR5 | Counter-tx for issuance only | 1 original + 1 counter `SALE_ISSUANCE`; collections block reversal | [`Operation._implicit_reversable_transaction_types`](../../apps/app_operation/models/operation.py:479) | [`test_reverse_creates_counter_transaction_for_issuance`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:157) |
| SR6 | Counter-tx flips funds | `counter.source == original.target`, `counter.target == original.source` | [`Transaction.reverse()`](../../apps/app_transaction/models.py:207) | [`test_reverse_counter_transaction_flips_funds`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:168) |
| SR7 | Fund balances unchanged | issuance is non-cash; reversal leaves fund balances untouched | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) | [`test_fund_balances_unchanged_after_reversal`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:178) |
| SR8 | Project receivables restored | `project.receivables` back to `0.00` | [`receivables_at`](../../apps/app_entity/models/__init__.py:511) | [`test_reverse_restores_project_receivables`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:195) |
| SR9 | Client payables restored | `client.payables` back to `0.00` | [`payables_at`](../../apps/app_entity/models/__init__.py:476) | [`test_reverse_restores_client_payables`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:202) |
| SR10 | Differential invariant | create + reverse leaves balances, payables, receivables and ledger unchanged | whole engine | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:223) |
| SR11 | Product status restored to ACTIVE | reversing the sale excludes the SOLD link, so the product returns to ACTIVE | [`Product.status`](../../apps/app_inventory/models.py) | [`test_reverse_restores_sold_product_to_active`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:337) |
| SR12 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:226) | implied by reversal tests |

### 5.3 `pay` (collection)

Standalone action — from the wizard (step 3, optional initial payment), later from the sale detail page, or via [`record_transaction_payment`](../../apps/app_operation/views/record_transaction.py:17). Model entry points: `create_payment_transaction()` / `process_payment()`.

#### 5.3.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VP1 | Balance enforced per collection (internal client) | `payment_source_fund.can_pay(amount)` | `ValidationError` | `"Insufficient funds: fund balance …"` | [`create_payment_transaction`](../../apps/app_base/mixins.py:377) | [`test_check_balance_on_payment_is_enabled`](../../apps/app_operation/tests/operations/sale/test_sale_sale_balance_guard.py:126), [`test_collection_blocked_when_internal_client_fund_has_insufficient_balance`](../../apps/app_operation/tests/operations/sale/test_sale_sale_balance_guard.py:144) |
| VP1b | External client exempt from balance check | `client.is_internal` is False | no check | — (collection proceeds; balance may go negative) | [`Entity.can_pay`](../../apps/app_entity/models/__init__.py:704) virtual exemption | [`test_collection_allowed_when_external_client_fund_has_insufficient_balance`](../../apps/app_operation/tests/operations/sale/test_sale_sale_balance_guard.py:130) |
| VP2 | Amount > 0 | `amount > 0` | `ValidationError` | `"The amount should be more than 0"` | [`validate_settlement_amount`](../../apps/app_base/mixins.py:318) | [`test_zero_collection_raises_validation_error`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:220) |
| VP3 | Amount ≤ remaining (over-collection guard) | `amount <= amount_remaining_to_settle` | `ValidationError` | `"The paid amount … exceeds the remaining …"` | [`validate_settlement_amount`](../../apps/app_base/mixins.py:320) | [`test_collection_exceeding_operation_amount_raises_validation_error`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:210), [`test_partial_collection_then_over_collection_raises_validation_error`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:214) |
| VP4 | Negative blocked | `amount > 0` | `ValidationError` | same as VP2 | [`validate_settlement_amount`](../../apps/app_base/mixins.py:318) | [`test_negative_collection_raises_validation_error`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:224) |
| VP5 | Partial allowed — multiple collections | `max_payment_transaction_count == -1` | — | — | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:342) | [`test_multiple_partial_collections_are_allowed`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:154) |
| VP6 | Collection date not in a closed period | `period_entity` open on `date` | `ValidationError` | `"Cannot record a payment dated within a closed financial period."` | [`create_payment_transaction`](../../apps/app_base/mixins.py:370) | covered by period suite |

#### 5.3.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SP1 | Collection tx created | 1 × `SALE_COLLECTION`, `client.fund → project.fund` | [`create_payment_transaction`](../../apps/app_base/mixins.py:410) | [`test_collection_creates_sale_collection_transaction`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:134), [`test_collection_transaction_direction_is_client_to_project`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:142) |
| SP2 | Remaining decreases | `amount_remaining_to_settle` ↓ by collection | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:301) | [`test_amount_remaining_to_settle_decreases_after_collection`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:149) |
| SP3 | Settled accumulates | `amount_settled = Σ collections` | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:269) | [`test_multiple_collections_accumulate_correctly`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:165) |
| SP4 | Full collection → fully settled | `is_fully_settled`, remaining `0.00` | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:307) | [`test_full_collection_marks_operation_as_fully_settled`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:172) |
| SP5 | Client fund ▼ | `client.balance` decreases by collection (cash) | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) | [`test_client_fund_decreases_by_collection_amount`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:178) |
| SP6 | Project fund ▲ | `project.balance` increases by collection | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) | [`test_project_fund_increases_by_collection_amount`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:189) |
| SP7 | Tx count after partial collection | 1 issuance + 1 collection = 2 | — | [`test_total_transactions_after_partial_collection_is_two`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:200) |

### 5.4 `move items`

Dispatching sold goods out of the selling project — from the wizard (invoice step), later from the sale detail page, or via [`create_inventory_movement`](../../apps/app_inventory/views.py:642). The wizard path uses [`create_from_session`](../../apps/app_operation/models/proxies/op_sale.py:204).

#### 5.4.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VM1 | Operation not reversed; movements enabled | `can_create_movement=True`; no active reversal | `ValidationError` | — | [`Operation.reverse()`](../../apps/app_operation/models/operation.py:1056) + stock layer | covered by inventory suite |
| VM2 | Qty ≤ item remaining qty | `moved_qty ≤ adjusted_quantity − moved` | `ValidationError` | — | [`active_lines_for_item`](../../apps/app_inventory/stock.py:51) | covered by inventory suite |
| VM3 | Product allowed + officer valid | product active/obligated; officer staff + active | `ValidationError` | — | [`InventoryMovementLine.save()`](../../apps/app_inventory/models.py:1202) | covered by inventory suite |
| VM4 | Inventory ownership | moved product must belong to the selling project | `ValidationError` | `"Selected product not found or does not belong to this project."` | [`create_from_session`](../../apps/app_operation/models/proxies/op_sale.py:167) | [`test_sale_rejects_product_not_owned_by_project`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:224), [`test_sale_movement_rejects_product_owned_by_another_entity`](../../apps/app_inventory/tests/test_inventory_movement.py:310) |
| VM5 | Availability | for a physically-present (received) product, qty must not exceed on-hand | `ValidationError` | `"Insufficient stock: … only %(avail)s available …"` | [`movement_state`](../../apps/app_inventory/stock.py) via [`create_from_session`](../../apps/app_operation/models/proxies/op_sale.py:179) | [`test_sale_over_sell_rejected_atomically`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:209), [`test_sale_movement_rejects_qty_beyond_on_hand`](../../apps/app_inventory/tests/test_inventory_movement.py:490) |
| VM6 | Unit consistency | qty must be a positive multiple of `product_template.minimum_quantity` | `ValidationError` | — | [`InventoryMovementLine.clean`](../../apps/app_inventory/models.py) | covered by inventory suite |
| VM7 | Operation/inventory type match | movement op type matches the view's op type | `ValidationError` | — | [`create_inventory_movement`](../../apps/app_inventory/views.py:642) | [`test_sale_movement_rejects_operation_mismatch`](../../apps/app_inventory/tests/test_inventory_movement.py:686) |

#### 5.4.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SM1 | `SALE_MOVEMENT` ledger entry | outbound movement against the seller's **existing** product; no new product minted | [`create_from_session`](../../apps/app_operation/models/proxies/op_sale.py:204) | [`test_sale_affects_existing_product_no_mint`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:118), [`test_sale_operation_movement`](../../apps/app_inventory/tests/test_inventory_movement.py:203) |
| SM2 | Product status SOLD; remaining ↓ | full disposal leaves `movement_state == 0`, status `SOLD` | [`Product.status`](../../apps/app_inventory/models.py) | [`test_sale_full_disposal_leaves_zero`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:147) |
| SM3 | Partial sale keeps ACTIVE | partial dispatch leaves remaining presence; status stays `ACTIVE` | [`Product.status`](../../apps/app_inventory/models.py) | [`test_sale_affects_existing_product_no_mint`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:142) |
| SM4 | INDIVIDUAL product sale | an individual (tagged) animal is moved qty 1, status `SOLD` | [`create_from_session`](../../apps/app_operation/models/proxies/op_sale.py:204) | [`test_sale_individual_animal_affected`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:161) |
| SM5 | Internal client receives buyer copy | inbound receipt movement for the client-owned clone (direction-aware) | [`create_from_session`](../../apps/app_operation/models/proxies/op_sale.py:221) | [`test_internal_client_receives_active_product`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:248) |
| SM6 | Movements reversible | reversing a movement (incl. the buyer's receipt) negates the ledger row | [`InventoryMovementLine`](../../apps/app_inventory/models.py) reversal | [`test_internal_client_receipt_movement_can_be_reversed`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:298) |

### 5.5 `adjust items`

Invoice-item correction (qty / unit price) via [`record_item_adjustment`](../../apps/app_operation/views/adjustment.py:135). This is the sanctioned way to change the sale issuance amount.

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
| SA3 | Inventory ledger entries | `*_ADJUSTMENT` ledger entries | [`InvoiceItemAdjustment.finalize()`](../../apps/app_adjustment/models.py) | covered by adjustment suite |

### 5.6 `adjust`

Accounting adjustment on the operation amount via [`record_accounting_adjustment`](../../apps/app_operation/views/adjustment.py:37). Adjusting changes `effective_amount` → the total sale amount, project receivables and client payables all change accordingly.

#### 5.6.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VA4 | Adjustable + not reversed / not a reversal | `is_adjustable=True`; no active reversal | `ValidationError` | — | [`Adjustment`](../../apps/app_adjustment/models.py) | covered by adjustment suite |
| VA5 | Adjustment type allowed for SALE | type maps to `SALE_ADJUSTMENT_INCREASE` / `SALE_ADJUSTMENT_DECREASE` | `ValidationError` | — | adjustment type map | covered by adjustment suite |
| VA6 | Amount > 0; officer staff + active | valid amount + officer | `ValidationError` | — | [`Adjustment`](../../apps/app_adjustment/models.py) | covered by adjustment suite |
| VA7 | Reduction can't drive below zero | `effective_amount ≥ 0` after reduction | `ValidationError` | — | [`Adjustment`](../../apps/app_adjustment/models.py) | covered by adjustment suite |

#### 5.6.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SA4 | Adjustment tx (non-cash) + `effective_amount` delta | `SALE_ADJUSTMENT_INCREASE` (`client → project`) / `SALE_ADJUSTMENT_DECREASE` (`project → client`); receivables/payables reflect delta | [`record_accounting_adjustment`](../../apps/app_operation/views/adjustment.py:37) + [`AdjustableMixin.effective_amount`](../../apps/app_base/mixins.py:96) | [`test_sale_adjustment_creates_sale_adjustment_transaction`](../../apps/app_adjustment/tests/test_adjustment_adjustment_transaction.py) |

### 5.7 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by [`ImmutableMixin`](../../apps/app_base/mixins.py:30) via `_immutable_fields` ([`operation.py`](../../apps/app_operation/models/operation.py:51)).

| Branch | Enforced by | Pinned by test |
|--------|-------------|----------------|
| `source` changed after save | `ImmutableMixin.save()` | [`test_source_is_immutable_after_save`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:315) |
| `destination` changed after save | `ImmutableMixin.save()` | [`test_destination_is_immutable_after_save`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:325) |
| `amount` changed after save | `ImmutableMixin.save()` | [`test_amount_is_immutable_after_save`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:335) |

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — [`Entity.save()`](../../apps/app_entity/models/__init__.py:714).
- The operation's governing entity (`period_entity`) is the **destination project** (`_dest_role = "url"`) — [`Operation.period_entity`](../../apps/app_operation/models/operation.py:491).
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC12).
- New operations dated inside a **closed** period are rejected (VC11) — [`is_date_in_closed_period`](../../apps/app_operation/models/period.py:14).
- **Collections** dated inside a closed period of the governing entity are rejected (VP6) — [`create_payment_transaction`](../../apps/app_base/mixins.py:370).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period ([`_reverse_period`](../../apps/app_operation/models/operation.py:455)).

---

## 7. Entity roles & balance contract

- **Source:** must be a **Client** that is an **active client stakeholder** of the destination project — enforced at model ([`clean_source`](../../apps/app_operation/models/proxies/op_sale.py:60)) and transaction ([`transaction_type.py`](../../apps/app_transaction/transaction_type.py:502)) layers (VC1/VC2/VC14).
- **Destination:** must be a **Project** — enforced at model ([`clean_destination`](../../apps/app_operation/models/proxies/op_sale.py:88)) and transaction (VC14) layers (VC3).
- `project.receivables` and `client.payables` are derived from **issuance + adjustment** types (non-cash) — [`receivables_at`](../../apps/app_entity/models/__init__.py:511) / [`payables_at`](../../apps/app_entity/models/__init__.py:476).
- `project.balance` and `client.balance` are derived exclusively from **payment-type** transactions (`SALE_COLLECTION`) — [`balance_at`](../../apps/app_entity/models/__init__.py:414).
- **Internal vs external client balance guard:** the project fund is a real fund, but the **payer** is the client fund. `check_balance_on_payment=True` guards each collection against the client fund — but only **internal** clients are balance-checked (VP1); **external** counterparties are exempt (`can_pay` returns `True` for virtual/external payers, VP1b). Issuance itself is unguarded (VC13).

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Create route | Wizard `GET/POST /<project_pk>/sale/wizard/` (+ `/…/<step>/`, `/cancel/`) → [`sale_wizard_view`](../../apps/app_operation/views/create_operation/sale_wizard.py:113); the generic create view redirects SALE to the wizard ([`base.py`](../../apps/app_operation/views/create_operation/base.py:131)) (URLs [`urls.py`](../../apps/app_operation/urls.py:97)) |
| Source selection | active **client stakeholders** of the project ([`get_related_entities`](../../apps/app_operation/models/proxies/op_sale.py:76)); picker on step 1 |
| Destination selection | locked to the **Project** from the URL (`_dest_role="url"`); no picker |
| Category | hidden (no category) |
| Amount | derived from invoice-item totals — wizard step 2 captures `total_amount`, validated by [`_validate_item_totals`](../../apps/app_operation/models/proxies/op_sale.py:143); user cannot manually diverge from item totals |
| POST parsing | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) |
| Invoice / items | [`sale_invoice_view`](../../apps/app_operation/views/create_operation/sale_wizard.py:280) (invoice page), [`sale_select_product_view`](../../apps/app_operation/views/create_operation/sale_wizard.py:341) (existing stock products), [`sale_add_item_view`](../../apps/app_operation/views/create_operation/sale_wizard.py:390) (add/edit), [`sale_delete_item_view`](../../apps/app_operation/views/create_operation/sale_wizard.py:486) (delete) |
| Initial collection | wizard step 3 — `amount_paid` (0 allowed); goes through `process_payment` |
| Record collection (later) | detail-page "Record Collection" → [`record_transaction_payment`](../../apps/app_operation/views/record_transaction.py:17); template [`add_payment_form.html`](../../apps/app_operation/templates/app_operation/add_payment_form.html) |
| Move items | wizard invoice step or detail-page shortcut → [`create_inventory_movement`](../../apps/app_inventory/views.py:642) |
| Adjust / adjust items | [`record_accounting_adjustment`](../../apps/app_operation/views/adjustment.py:37) / [`record_item_adjustment`](../../apps/app_operation/views/adjustment.py:135) |
| Submit | [`sale_submit_view`](../../apps/app_operation/views/create_operation/sale_wizard.py:506) → `SaleOperation.create_from_session()` (atomic) → redirects to operation detail |
| Detail | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) — total amount, collected so far, remaining; movement status; "Record Collection", adjust, and reversal actions |
| Reverse | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source=client · VC2 source active client stakeholder of dest · VC3 dest=project · VC4 source active · VC5 source fund active · VC6 dest active · VC7 target fund active · VC8 amount>0 · VC9 officer staff · VC10 officer active · VC11 not closed-period · VC12 covering period · VC13 issuance balance exempt · VC14 tx entity-type · VC15 tx op-type · VC16 source≠target

**create — effects:** SC1 issuance tx only · SC2 no collection tx · SC3 direction client→project · SC4 amount matches · SC5 non-cash (project unchanged) · SC6 client fund unchanged · SC7 remaining == amount · SC8 not fully settled · SC9 project receivables ▲ · SC10 client payables ▲ · SC11 project payables unchanged · SC12 client receivables unchanged · SC13 product linked; SOLD via SALE_MOVEMENT (not issuance) · SC14 internal client clone (ACTIVE) · SC15 external client no copy · SC16 period assigned

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no collections · VR4 no movements · VR5 no adjustments · VR6 reason required (view)

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 is_reversal · SR4 identity copied · SR5 counter-tx for issuance only · SR6 counter flips funds · SR7 fund balances unchanged · SR8 project receivables restored · SR9 client payables restored · SR10 differential invariant · SR11 product status restored to ACTIVE · SR12 reversal owns no txs

**pay (collection) — validation:** VP1 balance per collection (internal) · VP1b external client exempt · VP2 amount>0 · VP3 over-collection guard · VP4 negative blocked · VP5 partial/multiple allowed · VP6 closed-period blocked

**pay (collection) — effects:** SP1 collection tx client→project · SP2 remaining ↓ · SP3 settled accumulates · SP4 full → fully settled · SP5 client fund ▼ · SP6 project fund ▲ · SP7 tx count

**move items — validation:** VM1 not reversed · VM2 qty ≤ remaining · VM3 product/officer valid · VM4 ownership (selling project) · VM5 availability (≤ on-hand) · VM6 unit multiple · VM7 op-type match

**move items — effects:** SM1 SALE_MOVEMENT ledger, no mint · SM2 full disposal → SOLD/0 · SM3 partial → ACTIVE · SM4 individual animal moved · SM5 internal client buyer copy · SM6 movements reversible

**adjust items — validation:** VA1 adjustable + not reversed · VA2 ≥1 changed · VA3 qty ≥ moved · **effects:** SA1 item adjustment + lines · SA2 accounting adj + tx · SA3 ledger entries

**adjust — validation:** VA4 adjustable + not reversed · VA5 type allowed · VA6 amount>0/staff · VA7 reduction ≥ 0 · **effects:** SA4 `SALE_ADJUSTMENT_*` (non-cash) + `effective_amount` delta

**immutability:** IM1 source · IM2 destination · IM3 amount (all immutable after save)

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| Issuance tx count | [`test_save_creates_exactly_one_issuance_transaction`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:131), [`test_no_collection_transaction_created_on_save`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:137) | SC1, SC2 |
| Issuance direction + amount | [`test_issuance_transaction_direction_is_client_to_project`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:143), [`test_issuance_transaction_amount_matches_operation`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:151) | SC3, SC4 |
| Issuance non-cash | [`test_project_fund_balance_unchanged_after_save`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:158), [`test_client_fund_balance_unchanged_after_save`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:168) | SC5, SC6, VC13 |
| Settlement after create | [`test_amount_remaining_to_settle_equals_full_amount_after_creation`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:178), [`test_is_not_fully_settled_after_creation`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:184) | SC7, SC8 |
| Payables / receivables | [`test_create_project_receivables_increase`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:194), [`test_create_client_payables_increase`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:201), [`test_create_project_payables_unchanged`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:208), [`test_create_client_receivables_unchanged`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:214) | SC9–SC12 |
| Source validation | [`test_source_must_be_a_client_entity`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:224), [`test_source_project_entity_raises_validation_error`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:230), [`test_source_must_be_active`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:236), [`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:244) | VC1, VC4, VC5 |
| Destination / stakeholder validation | [`test_destination_must_be_a_project_entity`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:256), [`test_destination_must_be_active_stakeholder_project`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:262), [`test_destination_with_inactive_stakeholder_raises_validation_error`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:269) | VC3, VC2, VC6 |
| Amount / officer | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:281), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:286), [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:295), [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:303) | VC8–VC10 |
| Immutability | [`test_source_is_immutable_after_save`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:315), [`test_destination_is_immutable_after_save`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:325), [`test_amount_is_immutable_after_save`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create.py:335) | IM1–IM3 |
| Collection happy path | [`test_collection_creates_sale_collection_transaction`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:134), [`test_collection_transaction_direction_is_client_to_project`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:142) | SP1 |
| Collection settlement | [`test_amount_remaining_to_settle_decreases_after_collection`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:149), [`test_multiple_partial_collections_are_allowed`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:154), [`test_multiple_collections_accumulate_correctly`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:165), [`test_full_collection_marks_operation_as_fully_settled`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:172) | SP2–SP4, VP5 |
| Collection fund movement | [`test_client_fund_decreases_by_collection_amount`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:178), [`test_project_fund_increases_by_collection_amount`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:189) | SP5, SP6 |
| Over-collection / zero / negative | [`test_collection_exceeding_operation_amount_raises_validation_error`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:210), [`test_partial_collection_then_over_collection_raises_validation_error`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:214), [`test_zero_collection_raises_validation_error`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:220), [`test_negative_collection_raises_validation_error`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:224) | VP2, VP3, VP4 |
| Tx count | [`test_total_transactions_after_partial_collection_is_two`](../../apps/app_operation/tests/operations/sale/test_sale_sale_collection.py:200) | SP7 |
| Balance guard | [`test_check_balance_on_payment_is_enabled`](../../apps/app_operation/tests/operations/sale/test_sale_sale_balance_guard.py:126), [`test_collection_allowed_when_external_client_fund_has_insufficient_balance`](../../apps/app_operation/tests/operations/sale/test_sale_sale_balance_guard.py:130), [`test_collection_blocked_when_internal_client_fund_has_insufficient_balance`](../../apps/app_operation/tests/operations/sale/test_sale_sale_balance_guard.py:144), [`test_collection_succeeds_when_amount_within_client_fund_balance`](../../apps/app_operation/tests/operations/sale/test_sale_sale_balance_guard.py:158) | VP1, VP1b |
| Reverse happy path | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:131), [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:137), [`test_reversal_is_marked_as_reversal`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:144), [`test_reverse_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:150) | SR1–SR4 |
| Reverse counter-tx | [`test_reverse_creates_counter_transaction_for_issuance`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:157), [`test_reverse_counter_transaction_flips_funds`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:168) | SR5, SR6 |
| Reverse balances/payables | [`test_fund_balances_unchanged_after_reversal`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:178), [`test_reverse_restores_project_receivables`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:195), [`test_reverse_restores_client_payables`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:202), [`test_reverse_project_payables_unchanged`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:209), [`test_reverse_client_receivables_unchanged`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:214) | SR7–SR9 |
| Reverse constraints | [`test_reversal_blocked_when_collection_exists`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:246), [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:260), [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:267) | VR1, VR2, VR3 |
| Differential invariant | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:223) | SR10 |
| Product status (movement-driven) | [`test_sale_full_disposal_leaves_zero`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:147), [`test_sale_individual_animal_affected`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:161), [`test_sale_affects_existing_product_no_mint`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:118) | SC13, SM2, SM3, SM4 |
| Product status (reversal restoration) | [`test_reverse_restores_sold_product_to_active`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:337), [`test_sale_links_product_as_sold`](../../apps/app_operation/tests/operations/sale/test_sale_sale_reversal.py:331) | SR11, SC13 (no-movement fallback) |
| Wizard — affects existing product | [`test_sale_affects_existing_product_no_mint`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:118), [`test_sale_full_disposal_leaves_zero`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:147), [`test_sale_individual_animal_affected`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:161) | SM1–SM4 |
| Wizard — availability/ownership | [`test_sale_over_sell_rejected_atomically`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:209), [`test_sale_rejects_product_not_owned_by_project`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:224) | VM5, VM4 |
| Wizard — issuance + internal client | [`test_sale_issuance_transaction_created`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:235), [`test_internal_client_receives_active_product`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:248), [`test_external_client_gets_no_buyer_copy`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:285), [`test_internal_client_receipt_movement_can_be_reversed`](../../apps/app_operation/tests/operations/sale/test_sale_sale_create_from_session.py:298) | SC14, SC15, SM5, SM6 |
| Movement (sale) | [`test_sale_operation_movement`](../../apps/app_inventory/tests/test_inventory_movement.py:203), [`test_sale_movement_rejects_product_owned_by_another_entity`](../../apps/app_inventory/tests/test_inventory_movement.py:310), [`test_sale_movement_accepts_product_owned_by_selling_project`](../../apps/app_inventory/tests/test_inventory_movement.py:343), [`test_sale_movement_rejects_qty_beyond_on_hand`](../../apps/app_inventory/tests/test_inventory_movement.py:490), [`test_sale_movement_rejects_operation_mismatch`](../../apps/app_inventory/tests/test_inventory_movement.py:686) | SM1, VM4, VM5, VM7 |
| Adjust — transaction | [`test_sale_adjustment_creates_sale_adjustment_transaction`](../../apps/app_adjustment/tests/test_adjustment_adjustment_transaction.py) | SA4 |

---

## 11. Tasks

- [x] Verify save creates only one SALE_ISSUANCE transaction (not collection — not one-shot)
- [x] Verify no SALE_COLLECTION transaction is created on save
- [x] Verify SALE_ISSUANCE direction: source=client.fund, target=project.fund
- [x] Verify SALE_ISSUANCE is non-cash: project and client fund balances unchanged after save
- [x] Verify amount_remaining_to_settle equals full amount after creation
- [x] Verify is_not_fully_settled after creation
- [x] Verify source must be a Client entity (non-client source raises ValidationError)
- [x] Verify project entity as source raises ValidationError
- [x] Verify source must be an active client stakeholder of the destination project (non-stakeholder + inactive stakeholder raise ValidationError)
- [x] Verify source must be active (inactive source raises ValidationError)
- [x] Verify source fund must be active
- [x] Verify destination must be a Project entity (non-project destination raises ValidationError)
- [x] Verify amount/officer validations (zero, negative, non-staff, inactive)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify collection creates SALE_COLLECTION transaction (direction: client.fund → project.fund)
- [x] Verify collection amount_remaining_to_settle decreases correctly
- [x] Verify multiple partial collections are allowed and accumulate
- [x] Verify full collection marks operation as fully settled
- [x] Verify client fund decreases by collection amount (SALE_COLLECTION is cash)
- [x] Verify project fund increases by collection amount
- [x] Verify collection cannot exceed remaining amount (over-collection raises ValidationError)
- [x] Verify partial then over-collection raises ValidationError
- [x] Verify zero/negative collection raises ValidationError
- [x] Verify balance enforced on collection for internal clients; external client funds exempt
- [x] Reversal creates reversal operation with correct linkage
- [x] Verify reversal marks original as reversed
- [x] Verify reversal is marked as is_reversal
- [x] Verify reversal inherits amount, source, destination from original
- [x] Verify reversal creates counter-transaction for issuance only
- [x] Verify reversal counter-transaction flips source/target funds
- [x] Verify fund balances unchanged after reversal (issuance is non-cash)
- [x] Verify payables/receivables restored after reversal (project receivables, client payables)
- [x] Verify reversal is blocked when any SALE_COLLECTION transaction exists
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [x] Verify create + reverse differential invariant (balances/payables/receivables/ledger unchanged)
- [x] Verify a sale affects the seller's existing product (SALE_MOVEMENT, no mint); status SOLD on full disposal, ACTIVE on partial
- [x] Verify internal-client sale transfers goods (buyer ACTIVE clone + inbound receipt); external client gets no copy
- [x] Verify availability (≤ on-hand) and ownership (selling project) guards on move items
- [x] Verify movement lines (incl. internal-client receipt) are reversible
- [ ] Pin movement-reversal guard (VR4: reverse blocked while non-reversed movement lines exist) with a focused sale test
- [ ] Pin adjust-items / adjust branches (VA1–VA7, SA1–SA4) with focused sale tests
- [ ] Pin closed-period collection guard (VP6) with a focused sale test
- [ ] UI: create form — source=Client (from stakeholders), destination=Project (url entity), optional invoice formset
- [ ] UI: detail shows total amount, collected so far, remaining; "Record Collection" button
- [ ] Complete test coverage matrix §10 for every branch (mark tasks `[x]` once pinned)
