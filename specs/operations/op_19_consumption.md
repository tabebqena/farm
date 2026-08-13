# Consumption — Operation Contract

**Epic:** Inventory / Livestock — One-Shot
**Type:** One-shot, auto-settled, removes assets (`has_invoice=True`)
**Actions:** `create`, `reverse` (auto `move items`)
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Consumption** operation.
> Every clause below is registered to its implementing code (model → mixin → transaction → view) and to its pinning test.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> See [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md) for the shared structure and
> [`op_1_cash_injection.md`](op_1_cash_injection.md) for a fully worked example.

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.CONSUMPTION` (`"CONSUMPTION"`) | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:23) |
| Proxy class | `ConsumptionOperation` | [`op_consumption.py`](../../apps/app_operation/models/proxies/op_consumption.py:7) |
| URL slug | `"consumption"` | [`op_consumption.py`](../../apps/app_operation/models/proxies/op_consumption.py:19) |
| Label | `"Consumption"` | [`op_consumption.py`](../../apps/app_operation/models/proxies/op_consumption.py:20) |
| Theme | `danger` / `bi-box-arrow-up-right` (inherited default) | [`operation.py`](../../apps/app_operation/models/operation.py:112) |
| Source role | `url` (must be a Project) | [`op_consumption.py`](../../apps/app_operation/models/proxies/op_consumption.py:21) |
| Destination role | `system` | [`op_consumption.py`](../../apps/app_operation/models/proxies/op_consumption.py:22) |
| Registered in | `PROXY_MAP` | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:45) |
| Cross-op reference | row CO | [`operations-comparison.md`](operations-comparison.md) |

**Configuration flags** (all on [`op_consumption.py`](../../apps/app_operation/models/proxies/op_consumption.py:7)):

| Flag | Value | Meaning |
|------|-------|---------|
| `_issuance_transaction_type` | `CONSUMPTION_ISSUANCE` | issuance tx created on save |
| `_payment_transaction_type` | `CONSUMPTION_PAYMENT` | payment tx created on save (one-shot) — **non-cash bookkeeping** |
| `_is_one_shot_operation` | `True` | payment fires at create; no standalone pay action |
| `can_pay` | `False` | `process_payment()` is a no-op |
| `is_partially_payable` | `False` | payment must equal amount (one-shot) |
| `max_payment_transaction_count` | `1` | exactly one payment tx ever |
| `check_balance_on_payment` | `False` | write-off — no fund-balance check at create |
| `has_category` / `category_required` | `False` | no financial category |
| `has_repayment` | `False` | no repayment action |
| `has_invoice` | `True` | invoice items (selected existing products) + auto inventory movements |
| `creates_assets` | `False` | links to **existing** assets; no lazy product creation |
| `is_adjustable` / `is_items_adjustable` | `False` (inherited) | no accounting or item adjustments |

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row links the clause to the code that must honor it.

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_source`/`clean_destination` + payment funds + `project` | [`op_consumption.py`](../../apps/app_operation/models/proxies/op_consumption.py:7) |
| Proxy registry / URL→class resolution | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:45) |
| Shared `Operation` engine (`clean`, `save`, `reverse`, `create`, `resolve_request`, `save_inventory`, `_auto_create_inventory_movements`, reversal dependency guard, period assignment, reversable tx types) | [`operation.py`](../../apps/app_operation/models/operation.py:34) |
| Operation type enum | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:23) |

### 2.2 Core engine (mixins / base)

| Concern | Implementing code |
|---------|-------------------|
| Immutability of `source`/`destination`/`amount`/`period` | [`ImmutableMixin`](../../apps/app_base/mixins.py:30) + `_immutable_fields` in [`operation.py`](../../apps/app_operation/models/operation.py:51) |
| Amount must be > 0 | [`AmountCleanMixin`](../../apps/app_base/mixins.py:64) |
| Officer must be staff + active | [`OfficerMixin`](../../apps/app_base/mixins.py:80) |
| Source fund exists + active | [`SourceFundMixin`](../../apps/app_base/mixins.py:127) |
| Target fund exists + active | [`TargetFundMixin`](../../apps/app_base/mixins.py:147) |
| Issuance tx creation on save | [`LinkedIssuanceTransactionMixin`](../../apps/app_base/mixins.py:184) |
| One-shot payment tx creation + settlement (`amount_settled`, `is_fully_settled`) | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:242) |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | [`ReversableModel`](../../apps/app_base/models.py:133) + [`Operation.reverse()`](../../apps/app_operation/models/operation.py:997) |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | [`models.py`](../../apps/app_transaction/models.py:33) |
| `CONSUMPTION_ISSUANCE` (project → system, no balance) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:313), entity map [:550](../../apps/app_transaction/transaction_type.py:550), op map [:633](../../apps/app_transaction/transaction_type.py:633), issuance set [:477](../../apps/app_transaction/transaction_type.py:477) |
| `CONSUMPTION_PAYMENT` (project → system, **non-cash — excluded from `payment_types()`**) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:320), entity map [:551](../../apps/app_transaction/transaction_type.py:551), op map [:634](../../apps/app_transaction/transaction_type.py:634), payment set (excluded) [:417](../../apps/app_transaction/transaction_type.py:417) |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Balance derivation (payment types only — `CONSUMPTION_PAYMENT` excluded, so consumption never drains a fund balance) | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) |
| COGS in P&L (`CONSUMPTION_ISSUANCE` counted as a cost; its reversal offset restores profit) | [`Entity.profit_loss`](../../apps/app_entity/models/__init__.py:546) |
| Virtual/system-entity payment exemption | [`Entity.can_pay`](../../apps/app_entity/models/__init__.py:704) |
| Open financial period auto-created on entity creation | [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) |
| Period `end_assets` = cash + movement-based inventory + loans + advances (consumption leaves via inventory, not cash) | [`FinancialPeriod.end_assets`](../../apps/app_operation/models/period.py:390) |

### 2.5 Inventory layer (consumption-specific)

| Concern | Implementing code |
|---------|-------------------|
| Consumable template gating: FEED/MEDICINE nature **and** `can_be_consumed=True`; ANIMAL always rejected | [`models.py`](../../apps/app_inventory/models.py:161) (`accepts_operation`), `can_be_consumed` gating [:170](../../apps/app_inventory/models.py:170), nature allow-list [:155](../../apps/app_inventory/models.py:155) |
| Product selection (existing asset, not created) — `InvoiceItemSelectFormSet` | [`operation.py`](../../apps/app_operation/models/operation.py:416) + `_build_formset` in [`base.py`](../../apps/app_operation/views/create_operation/base.py:33) |
| Ownership guard: selected product belongs to the source project | [`save_inventory`](../../apps/app_operation/models/operation.py:850) + [`InventoryMovementLine.clean`](../../apps/app_inventory/models.py:1147) |
| Availability guard: quantity ≤ physically-present on-hand (movement-ledger) | [`_validate_availability`](../../apps/app_inventory/models.py:1055) + [`InventoryMovementLine.clean`](../../apps/app_inventory/models.py:1157) |
| Unit consistency: quantity multiple of `product_template.minimum_quantity` | [`InventoryMovementLine.clean`](../../apps/app_inventory/models.py:1159) |
| Auto outbound movement lines; product status CONSUMED; restored to ACTIVE on reversal | [`operation.py`](../../apps/app_operation/models/operation.py:950), [`Product.status`](../../apps/app_inventory/models.py:613) |
| Movement-based valuation (`movement_state`, `inventory_value`) — consumed value leaves inventory **once**; the movement line **is** the ledger (no separate `ProductLedgerEntry` table) | [`stock.py`](../../apps/app_inventory/stock.py:111), `inventory_value` [:143](../../apps/app_inventory/stock.py:143), `_OUTBOUND_TYPES` [:14](../../apps/app_inventory/stock.py:14) |
| Reversal dependency guard (products moved again later) | [`Operation.reverse()`](../../apps/app_operation/models/operation.py:1014) |

### 2.6 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (generic — resolves the project URL source + system destination, builds the select formset) | [`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:75) |
| POST parsing/validation | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) |
| Quick-consume view (one-step from stock detail) | [`quick_consume`](../../apps/app_inventory/views.py:318) |
| Reverse view (reason required) | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) |
| Detail view (transactions + reversal button) | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) |
| URL: `/<pk>/<op_type>/create` (op_type = `consumption`) | [`urls.py`](../../apps/app_operation/urls.py:142) |
| URL: `entity/<int:entity_pk>/stock/consume/` (name `quick_consume`) | [`app_inventory/urls.py`](../../apps/app_inventory/urls.py:20) |
| URL: `/<pk>/reverse/` | [`urls.py`](../../apps/app_operation/urls.py:192) |
| URL: `/<pk>/detail/` | [`urls.py`](../../apps/app_operation/urls.py:182) |
| Templates | [`generic_form.html`](../../apps/app_operation/templates/app_operation/generic_form.html), [`reverse_form.html`](../../apps/app_operation/templates/app_operation/reverse_form.html), [`operation_detail.html`](../../apps/app_operation/templates/app_operation/operation_detail.html), entry link in [`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html) |

### 2.7 Tests

| Concern | Test file |
|---------|-----------|
| Create branches (movement lines, status, tx, settlement, COGS, non-cash) | [`test_consumption_consumption_create.py`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py) |
| Reverse branches (reversal record, counter-tx, auto lines reversed, ledger negation, status CONSUMED→ACTIVE, COGS negated) | [`test_consumption_consumption_reversal.py`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_reversal.py) |
| Stock detail/history UI branches | [`test_consumption_stock_detail.py`](../../apps/app_operation/tests/operations/inventory/test_consumption_stock_detail.py) |
| One-step quick-consume branches | [`test_quick_consume_from_stock.py`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py) |
| Coverage manifest (executable branch registry) | [`tests/base.py`](../../apps/app_operation/tests/base.py:670) |

---

## 3. Money flow & entities

- **Source (payer):** the **Project** entity in the URL (`is_project=True`). Its fund is the source fund; the project owns the consumed asset.
- **Destination (receiver):** the single **System** entity (`is_system=True`). Virtual — never balance-checked, exempt from fund-balance validation (`payment_target_fund`).
- **Transaction flow** (both on create, project → system):

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `CONSUMPTION_ISSUANCE` | `project.fund → system.fund` | none (issuance, not a payment type) |
| 2 | `CONSUMPTION_PAYMENT` | `project.fund → system.fund` | **none** — non-cash bookkeeping, **excluded from `payment_types()`** |

- **Payment source fund:** `self.source` (project) — [`op_consumption.py`](../../apps/app_operation/models/proxies/op_consumption.py:38)
- **Payment target fund:** `self.destination` (system) — [`op_consumption.py`](../../apps/app_operation/models/proxies/op_consumption.py:42)

> **No cash flow — COGS (Option B).** Consumed feed/medicine is recognized as **Cost of Goods Sold (COGS)** that reduces the project's own profit in the period it is consumed — matching the feed cost to the period of the milk/meat revenue it helps produce.
> - `CONSUMPTION_ISSUANCE` is counted in [`Entity.profit_loss()`](../../apps/app_entity/models/__init__.py:546) costs, so the P&L and `FinancialPeriod.amount` reflect consumed feed/medicine in the consumption period.
> - `CONSUMPTION_PAYMENT` is **not** a payment type anymore (removed from [`TransactionType.payment_types()`](../../apps/app_transaction/transaction_type.py:417)), so consumption does **not** drain the fund balance (`balance_at()` is unchanged). The consumed value moves from the inventory asset (movement ledger) to COGS on the P&L — a clean internal transfer on the project's books.
> - `end_assets` (cash balance + remaining inventory) and the P&L both reflect consumption **exactly once**.
> - Reversal of a consumption negates the COGS: the reversal issuance restores profit and keeps the fund balance unchanged.

---

## 4. Settlement model

Derived from [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:242) using payment-type transactions only (note: `CONSUMPTION_PAYMENT` is **not** a payment type for balance purposes, but it *is* the one-shot settlement transaction for this operation):

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

Entry points: model `ConsumptionOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx, then payment tx), then the invoice formset → `save_inventory()` → `_auto_create_inventory_movements()`.

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source is Project | `source.is_project` | `ValidationError` | `"Consumption source must be a Project entity."` | [`clean_source`](../../apps/app_operation/models/proxies/op_consumption.py:50) | model clean (mirror of [`op_18`](op_18_death.md) VC1) |
| VC2 | Destination is System | `destination.is_system` | `ValidationError` | `"Consumption destination must be the System entity."` | [`clean_destination`](../../apps/app_operation/models/proxies/op_consumption.py:54) | model clean (mirror of [`op_18`](op_18_death.md) VC2) |
| VC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | shared engine suite |
| VC4 | Destination entity active | `destination.active` | `ValidationError` | same as VC3 | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | shared engine suite |
| VC5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | [`SourceFundMixin`](../../apps/app_base/mixins.py:132) | shared engine suite |
| VC6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | [`TargetFundMixin`](../../apps/app_base/mixins.py:152) | shared engine suite |
| VC7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | [`AmountCleanMixin`](../../apps/app_base/mixins.py:69) | shared engine suite |
| VC8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:81) | [`test_quick_consume_requires_officer`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py:194) (view), shared engine suite (model) |
| VC9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:84) | shared engine suite |
| VC10 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:541) | period suite |
| VC11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) | period suite |
| VC12 | Balance exempt (write-off) | no balance check | never fails | — | `check_balance_on_payment=False` | structural (`can_pay`-less one-shot) |
| VC13 | Tx entity-type contract | `source.is_project` and `target.is_system` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | [`Transaction.create()`](../../apps/app_transaction/models.py:144) + map [:550](../../apps/app_transaction/transaction_type.py:550) | implied by VC1/VC2 (model clean blocks first) |
| VC14 | Tx operation-type allowed | document is `CONSUMPTION` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | [`Transaction.create()`](../../apps/app_transaction/models.py:155) + map [:633](../../apps/app_transaction/transaction_type.py:633) | implied by VC1/VC2 |
| VC15 | Source ≠ target | project ≠ system | always true | `"Source and target funds must be different."` | [`Transaction.clean()`](../../apps/app_transaction/models.py:107) | structural (project ≠ system) |
| VC16 | Template is consumable | `nature ∈ {FEED, MEDICINE}` **and** `can_be_consumed=True` (ANIMAL is always rejected — `can_be_consumed` forced off) | `ValidationError` | template rejected by `accepts_operation(CONSUMPTION)` | [`ProductTemplate.accepts_operation`](../../apps/app_inventory/models.py:161) + nature allow-list [:155](../../apps/app_inventory/models.py:155) | [`test_quick_consume_rejects_non_consumable_nature`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py:207), [`test_quick_consume_rejects_non_consumable_flag`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py:246) |
| VC17 | Product linked (must be an existing asset) | `selected_product` present on the invoice item | form/`ValidationError` | missing-product error | [`InvoiceItemSelectFormSet`](../../apps/app_inventory/forms.py:290) + [`save_inventory`](../../apps/app_operation/models/operation.py:835) | implied by create flow ([`test_create_auto_creates_movement_line`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:113)) |
| VC18 | Ownership — product belongs to source project | `selected.entity == inventory_owner_entity` | `ValidationError` | `"Product '%(p)s' does not belong to '%(entity)s' and cannot be used in this operation."` | [`save_inventory`](../../apps/app_operation/models/operation.py:850) + [`InventoryMovementLine.clean`](../../apps/app_inventory/models.py:1147) | [`test_quick_consume_rejects_product_not_in_entity`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py:286), shared inventory suite |
| VC19 | Availability — quantity ≤ on-hand | `quantity ≤ movement_state(product, as_of=date)["quantity"]` | `ValidationError` | availability error | [`InventoryMovementLine.clean`](../../apps/app_inventory/models.py:1157) + [`_auto_create_inventory_movements`](../../apps/app_operation/models/operation.py:867) | [`test_quick_consume_over_consumption_is_rejected`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py:182), shared inventory suite |
| VC20 | Unit consistency | quantity is a multiple of `product_template.minimum_quantity` | `ValidationError` | unit-step error | [`InventoryMovementLine.clean`](../../apps/app_inventory/models.py:1159) | shared inventory suite |
| VC21 | Product not already terminal | `Product.status` is not CONSUMED/SOLD/DEAD/REMOVED (unless reversal/adjustment) | `ValidationError` | `"Product '%(id)s' has status %(status)s and cannot be used in new operations."` | [`Product.validate_active`](../../apps/app_inventory/models.py:760) | [`test_consumed_product_validate_active_blocks_reuse`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:192) |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | 1 × `CONSUMPTION_ISSUANCE`, amount `== op.amount`, `project → system` | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:222) | [`test_create_creates_issuance_and_payment_transactions`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:207) |
| SC2 | Payment tx created (non-cash) | 1 × `CONSUMPTION_PAYMENT`, amount `== op.amount`, `project → system`; **not** a `payment_types()` type → no balance/payable/receivable effect | [`LinkedPaymentTransactionMixin.save()`](../../apps/app_base/mixins.py:424) | same as SC1 |
| SC3 | Tx amounts equal op amount | both txs `amount == op.amount` (amount = Σ item quantity × unit_price) | [`_compute_amount`](../../apps/app_operation/views/create_operation/base.py:52) + transaction creation | [`test_create_is_fully_settled`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:220) |
| SC4 | Tx fund direction | both txs `source=project`, `target=system` | [`op_consumption.py`](../../apps/app_operation/models/proxies/op_consumption.py:38) | same as SC1 |
| SC5 | Fully settled immediately | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:268) | [`test_create_is_fully_settled`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:220) |
| SC6 | No cash flow | project fund balance unchanged (payment non-cash); system (virtual) ▲ in bookkeeping only | `payment_types()` exclusion + `Entity.balance_at` | [`test_create_does_not_drain_fund_balance`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:245) |
| SC7 | Auto outbound movement lines | one movement line per item at item qty (shared `group_key`), linked to the selected product, valued at the product's carried cost | [`_auto_create_inventory_movements`](../../apps/app_operation/models/operation.py:950) | [`test_create_auto_creates_movement_line`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:113), [`test_movement_line_uses_the_selected_product`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:129), [`test_movement_line_quantity_matches_invoice_item`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:139), [`test_multiple_items_each_get_a_movement_line_with_shared_group`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:146) |
| SC8 | Product status CONSUMED | the consumed product's movement-based `status == CONSUMED`; physically moved (not obligated-only) | [`Product.status`](../../apps/app_inventory/models.py:613) | [`test_create_marks_product_consumed`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:177), [`test_consumed_product_is_physically_moved`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:184) |
| SC9 | COGS — P&L reduced | `CONSUMPTION_ISSUANCE` counted in `profit_loss()` costs → `Entity.profit_loss()` drops by the consumed value in the consumption period; inventory value leaves **once** via `movement_state` (net presence → 0) | [`Entity.profit_loss`](../../apps/app_entity/models/__init__.py:634) + [`movement_state`](../../apps/app_inventory/stock.py:111) | [`test_create_reduces_profit_loss`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:232), [`test_create_writes_movement_and_issuance_ledger_entries`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:163) |
| SC10 | Period auto-assigned | `period` = the project's covering period (open period auto-created at entity creation) | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) + [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) | covered by period suite |

#### 5.1.3 `quick-consume` from stock (one-step shortcut)

A lightweight entry point on the stock detail page that removes the friction of the full consumption form for daily feeding: pick the product and a quantity, click **Consume**, and the whole pipeline runs in one POST.

- View: [`quick_consume()`](../../apps/app_inventory/views.py:318) — POSTs a minimal form (`product_id`, `quantity`, `unit_price`, optional `date`/`description`), builds the single-item formset internally, and delegates to the unchanged `ConsumptionOperation.create(...)` factory — so issuance + payment transactions, the auto movement line, and the CONSUMED product status all reuse the proven path (SC1–SC10).
- Route: `entity/<int:entity_pk>/stock/consume/` (name `quick_consume`) in [`apps/app_inventory/urls.py`](../../apps/app_inventory/urls.py:20).
- Guards are checked in the view for a friendly message **and again at the model layer** via `InventoryMovementLine.clean()` / `save_inventory()`:

| # | Guard | Pass condition | Friendly message (view) | Enforced by | Pinned by test |
|---|-------|----------------|-------------------------|-------------|----------------|
| QC1 | Officer | `request.user.is_staff` | `"You must be an officer to consume from stock."` | [`quick_consume`](../../apps/app_inventory/views.py:339) | [`test_quick_consume_requires_officer`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py:194) |
| QC2 | Ownership | `product.entity == entity` | `"Product does not belong to this stock."` | [`quick_consume`](../../apps/app_inventory/views.py:357) | [`test_quick_consume_rejects_product_not_in_entity`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py:286) |
| QC3 | Consumable nature + flag | `product_template.accepts_operation(CONSUMPTION)` (FEED/MEDICINE + `can_be_consumed`) | `"'%(name)s' cannot be consumed."` | [`quick_consume`](../../apps/app_inventory/views.py:362) | [`test_quick_consume_rejects_non_consumable_nature`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py:207), [`test_quick_consume_rejects_non_consumable_flag`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py:246) |
| QC4 | Quantity > 0 | `quantity > 0` | `"Quantity must be greater than zero."` | [`quick_consume`](../../apps/app_inventory/views.py:386) | structural (mirror of VC7 at line level) |
| QC5 | Availability | `quantity ≤ movement_state(product, as_of=date)["quantity"]` | `"Insufficient stock: %(qty)s requested but only %(avail)s available."` | [`quick_consume`](../../apps/app_inventory/views.py:390) | [`test_quick_consume_over_consumption_is_rejected`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py:182) |
| QC6 | Unit consistency | quantity multiple of `minimum_quantity` | `"Quantity %(qty)s must be a multiple of the minimum increment %(min)s."` | [`quick_consume`](../../apps/app_inventory/views.py:400) | shared inventory suite |
| QC7 | Date parseable | optional `date` field is a valid date | `"Invalid date format."` | [`quick_consume`](../../apps/app_inventory/views.py:376) | structural |
| QC8 | System entity available | a System entity exists (or is created) | — | [`quick_consume`](../../apps/app_inventory/views.py:410) | structural |

- Redirects back to the stock detail page on success or error (Django message). Success path verified by [`test_quick_consume_creates_full_pipeline`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py:109); partial consumption by [`test_quick_consume_partial_consumption`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py:170).

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:34) | shared engine suite (cf. [`op_1`](op_1_cash_injection.md) VR1) |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:47) | shared engine suite |
| VR3 | No explicit txs to reverse | all txs are implicit (one-shot issuance + payment) | `ValidationError` (would require manual reversal) | `"You can't reverse this object as it has non-reversed transactions…"` | [`ReversableModel._requires_transaction_reversal`](../../apps/app_base/models.py:203) + [`Operation._implicit_reversable_transaction_types`](../../apps/app_operation/models/operation.py:478) | implied by successful reverse ([`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_reversal.py:135)) |
| VR4 | Reversal dependency guard | none of the consumed products were moved again in a later non-reversed outbound op (SALE/DEATH/CONSUMPTION) | `ValidationError` | `"Cannot reverse this operation: its products were moved again in a later operation."` | [`Operation.reverse()`](../../apps/app_operation/models/operation.py:1014) | shared outbound-op suite (SALE/DEATH/CONSUMPTION) — **consumption-focused test pending** |
| VR5 | No non-reversed adjustments | n/a — Consumption is not adjustable | never fails | — | `is_adjustable=False` | n/a |
| VR6 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:82) | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:235) | [`test_reverse_creates_reversal_record`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_reversal.py:101) |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:270) | structural (same engine as [`op_1`](op_1_cash_injection.md) SR2) |
| SR3 | Reversal inherits identity | `amount`, `source`, `destination` copied | [`ReversableModel._get_reverse_kwargs`](../../apps/app_base/models.py:184) | structural (same engine as [`op_1`](op_1_cash_injection.md) SR3) |
| SR4 | Counter-tx for issuance | `system → project`, same amount, same type, `reversal_of=original` | [`Transaction.reverse()`](../../apps/app_transaction/models.py:206) | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_reversal.py:135) |
| SR5 | Counter-tx for payment | `system → project`, same amount, same type, `reversal_of=original` | same as SR4 | same as SR4 |
| SR6 | Counter-txs preserve type + amount | `counter.type == original.type`, `counter.amount == original.amount` | same as SR4 | same as SR4 |
| SR7 | Auto movement lines reversed | one reversal line per original (equal qty, `reversal_of` link, same product); originals preserved | [`Operation.reverse()`](../../apps/app_operation/models/operation.py:1070) → `line.reverse()` | [`test_reverse_reverses_auto_movement_lines`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_reversal.py:109), [`test_reverse_movement_ledger_negation_exact_set`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_reversal.py:151) |
| SR8 | Ledger negated | the consumed product's net presence restored to its pre-consumption on-hand (`qty`/`value` back to baseline) | [`movement_state`](../../apps/app_inventory/stock.py:111) | [`test_reverse_negates_ledger_entries`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_reversal.py:126) |
| SR9 | Product status restored to ACTIVE | reversal-aware `Product.status` → `ACTIVE` (reversal operations are excluded from the status derivation) | [`Product.status`](../../apps/app_inventory/models.py:613) | [`test_reversed_product_returns_to_active_status`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_reversal.py:170) |
| SR10 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:226) | shared engine (cf. [`op_1`](op_1_cash_injection.md) SR7) |
| SR11 | COGS negated — P&L restored | the reversal `CONSUMPTION_ISSUANCE` is a mirror tx (`target=fund`, `reversal_of` set) that `profit_loss()` negates → profit returns to pre-consumption baseline | [`Entity.profit_loss`](../../apps/app_entity/models/__init__.py:647) | [`test_reverse_restores_profit_loss`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_reversal.py:181) |
| SR12 | Fund balance unchanged | neither the consumption nor its reversal is a payment type → `balance_at()` unchanged throughout | `payment_types()` exclusion + `Entity.balance_at` | [`test_reverse_keeps_fund_balance_unchanged`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_reversal.py:194) |
| SR13 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger, inventory value, P&L) | whole engine | shared engine invariant |

### 5.3 `pay` (one-shot guard)

There is **no standalone pay action** for Consumption:

| Branch | Behavior | Enforced by | Pinned by test |
|--------|----------|-------------|----------------|
| `process_payment()` called | no-op (returns immediately — `can_pay=False`) | [`process_payment`](../../apps/app_operation/models/operation.py:686) | n/a (covered by `can_pay=False`) |
| `create_payment_transaction()` called after create | `ValidationError` — one-shot allows a single payment only, amount must equal `op.amount` | [`create_payment_transaction`](../../apps/app_base/mixins.py:391) | shared one-shot suite (cf. [`op_1`](op_1_cash_injection.md) BP2) |

### 5.4 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by [`ImmutableMixin`](../../apps/app_base/mixins.py:30) via `_immutable_fields` ([`operation.py`](../../apps/app_operation/models/operation.py:51)). Shared with every operation (see [`op_1`](op_1_cash_injection.md) §5.4).

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — [`Entity.save()`](../../apps/app_entity/models/__init__.py:714).
- The operation's governing entity (`period_entity`) is the **source project** (`_source_role = "url"`) — [`Operation.period_entity`](../../apps/app_operation/models/operation.py:491). The System (virtual) has no periods and is exempt.
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC11).
- New operations dated inside a **closed** period are rejected (VC10).
- `FinancialPeriod.amount` (closed project periods) is driven by the same issuance-based P&L, so consumed feed/medicine lands as COGS in the consumption period ([`FinancialPeriod.amount`](../../apps/app_operation/models/period.py:82)).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period ([`_reverse_period`](../../apps/app_operation/models/operation.py:455)).

---

## 7. Entity roles & balance contract

- Project is the only allowed source; System the only allowed destination — enforced at model (VC1/VC2) and transaction (VC13) layers.
- `CONSUMPTION_PAYMENT` is **deliberately excluded** from `payment_types()` ([`transaction_type.py`](../../apps/app_transaction/transaction_type.py:417)) — it is a non-cash bookkeeping record. The project's fund balance, payables and receivables are **never** affected by a consumption.
- The consumed asset's value is recognized **exactly once**, as **COGS** in [`Entity.profit_loss()`](../../apps/app_entity/models/__init__.py:546): `CONSUMPTION_ISSUANCE` is a cost (source=fund), and its reversal (target=fund, `reversal_of` set) is negated to restore profit (SC9/SR11). The movement-based `inventory_value()` drops by the carried cost at the same time.
- `FinancialPeriod.end_assets` = cash + movement-based inventory + loans + advances, so a consumption reduces `end_assets` exactly once, via inventory (not cash) — and the P&L counts it once as COGS.
- System is **virtual**: `can_pay` always returns `True`, so consumptions are never blocked by fund balance (VC12).

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Create route | `POST/GET /<project_pk>/consumption/create` → [`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:75) (generic; resolves the proxy via the `op_type` URL segment) |
| Source selection | the **Project** from the URL (`_source_role="url"`); no picker |
| Destination selection | locked to the single **System** entity (`_dest_role="system"`); no secondary-entity field |
| Category | hidden (no category) |
| Amount | computed from item totals (Σ quantity × unit_price) via [`_compute_amount`](../../apps/app_operation/views/create_operation/base.py:52); validated > 0 at model |
| Invoice items | `InvoiceItemSelectFormSet` (`creates_assets=False` → `_build_formset`) — one row per affected product, picking an **existing** product (`selected_product`) owned by the project |
| Consumable product | selectable products are those whose template is FEED/MEDICINE **and** `can_be_consumed=True` (`accepts_operation(CONSUMPTION)`); ANIMAL templates are never selectable |
| POST parsing | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) — date format, description, category (n/a), `amount_paid` (n/a, forced 0) |
| Quick-consume | stock detail `live` tab renders an inline form posting to `entity/<entity_pk>/stock/consume/` (name `quick_consume`) — see §5.1.3; redirects back to stock detail with a Django message |
| List entry | "Consumption" link in [`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html) |
| Detail | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) — shows both transactions + auto movement lines + settlement + reversal button |
| Stock history | the consumed product's OUT movement appears on the Stock History page ([`stock_history`](../../apps/app_inventory/views.py:173)); the `live` tab excludes CONSUMED products ([`stock_detail`](../../apps/app_inventory/views.py:25)) |
| Reverse | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source=project · VC2 dest=system · VC3 source active · VC4 dest active · VC5 source fund active · VC6 target fund active · VC7 amount>0 · VC8 officer staff · VC9 officer active · VC10 not closed-period · VC11 covering period exists · VC12 balance exempt · VC13 tx entity-type · VC14 tx op-type · VC15 source≠target · VC16 consumable FEED/MEDICINE (`can_be_consumed`) · VC17 product linked · VC18 ownership · VC19 availability ≤ on-hand · VC20 unit multiple · VC21 product not terminal

**create — effects:** SC1 issuance tx · SC2 non-cash payment tx · SC3 amounts equal · SC4 direction project→system · SC5 settled immediately · SC6 no cash flow · SC7 auto outbound lines · SC8 status CONSUMED · SC9 COGS (P&L ▼, inventory ▼ once) · SC10 period assigned

**quick-consume — guards:** QC1 officer staff · QC2 ownership · QC3 consumable nature + flag · QC4 quantity > 0 · QC5 availability ≤ on-hand · QC6 unit multiple · QC7 date parseable · QC8 system entity present

**quick-consume — effects:** QCS1 delegates to `ConsumptionOperation.create(...)` → SC1–SC10 full pipeline in one POST

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no explicit txs · VR4 reversal dependency guard · VR5 no adjustments (n/a) · VR6 reason required (view)

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 identity copied · SR4 issuance counter-tx · SR5 payment counter-tx · SR6 type/amount preserved · SR7 auto lines reversed · SR8 ledger negated · SR9 status restored to ACTIVE · SR10 reversal owns no txs · SR11 COGS negated (P&L restored) · SR12 fund balance unchanged · SR13 differential invariant

**pay / immutability:** BP1 `process_payment` no-op · BP2 `create_payment_transaction` blocked after create · IM1/IM2/IM3 source/destination/amount immutable

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| Auto movement line | [`test_create_auto_creates_movement_line`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:113), [`test_movement_line_uses_the_selected_product`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:129), [`test_movement_line_quantity_matches_invoice_item`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:139), [`test_multiple_items_each_get_a_movement_line_with_shared_group`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:146) | SC7, VC17 |
| Ledger / stock state | [`test_create_writes_movement_and_issuance_ledger_entries`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:163) | SC9 |
| Status CONSUMED | [`test_create_marks_product_consumed`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:177), [`test_consumed_product_is_physically_moved`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:184) | SC8 |
| Status reuse blocked | [`test_consumed_product_validate_active_blocks_reuse`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:192) | VC21 |
| Tx creation + counts | [`test_create_creates_issuance_and_payment_transactions`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:207) | SC1, SC2, SC4 |
| Settlement | [`test_create_is_fully_settled`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:220) | SC3, SC5 |
| COGS / P&L | [`test_create_reduces_profit_loss`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:232) | SC9 |
| Non-cash balance | [`test_create_does_not_drain_fund_balance`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py:245) | SC6 |
| Reverse happy path | [`test_reverse_creates_reversal_record`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_reversal.py:101) | SR1 |
| Auto lines reversed | [`test_reverse_reverses_auto_movement_lines`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_reversal.py:109), [`test_reverse_movement_ledger_negation_exact_set`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_reversal.py:151) | SR7, SR8 |
| Ledger negation | [`test_reverse_negates_ledger_entries`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_reversal.py:126) | SR8 |
| Counter txs | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_reversal.py:135) | SR4–SR6, VR3 |
| Status restored ACTIVE | [`test_reversed_product_returns_to_active_status`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_reversal.py:170) | SR9 |
| COGS negated (P&L restored) | [`test_reverse_restores_profit_loss`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_reversal.py:181) | SR11 |
| Non-cash balance on reverse | [`test_reverse_keeps_fund_balance_unchanged`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_reversal.py:194) | SR12 |
| Stock history shows OUT | [`test_consumed_product_movement_in_stock_history`](../../apps/app_operation/tests/operations/inventory/test_consumption_stock_detail.py:100) | SC7, SC8 (UI) |
| Live tab excludes consumed | [`test_live_stock_excludes_consumed_product`](../../apps/app_operation/tests/operations/inventory/test_consumption_stock_detail.py:119) | SC8 (UI) |
| Quick-consume full pipeline | [`test_quick_consume_creates_full_pipeline`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py:109) | QCS1, SC1–SC10 |
| Quick-consume form renders | [`test_stock_detail_renders_quick_consume_form`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py:152) | QC (UI) |
| Quick-consume partial | [`test_quick_consume_partial_consumption`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py:170) | QCS1 (partial) |
| Quick-consume availability | [`test_quick_consume_over_consumption_is_rejected`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py:182) | QC5, VC19 |
| Quick-consume officer | [`test_quick_consume_requires_officer`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py:194) | QC1, VC8 |
| Quick-consume nature | [`test_quick_consume_rejects_non_consumable_nature`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py:207), [`test_quick_consume_rejects_non_consumable_flag`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py:246) | QC3, VC16 |
| Quick-consume ownership | [`test_quick_consume_rejects_product_not_in_entity`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py:286) | QC2, VC18 |

---

## 11. Tasks

- [x] Verify `CONSUMPTION_ISSUANCE` + `CONSUMPTION_PAYMENT` created on save (non-cash payment)
- [x] Verify transaction fund direction: `project.fund → system.fund` for both
- [x] Verify operation is fully settled immediately
- [x] Verify `CONSUMPTION_PAYMENT` is excluded from `payment_types()` → no balance / payable / receivable effect
- [x] Verify `CONSUMPTION_ISSUANCE` is counted as **COGS** in `Entity.profit_loss()` (P&L reduced once; `end_assets` reduced once via inventory)
- [x] Verify all validation branches VC1–VC21 (VC16–VC21 consumable/ownership/availability/unit/status rules)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `create_payment_transaction()` is blocked after creation (one-shot)
- [x] Verify auto outbound movement lines and product status CONSUMED
- [x] Verify reversal creates counter-transactions `system.fund → project.fund` and reverses auto lines
- [x] Verify product status restored to ACTIVE on reversal (reversal-aware `Product.status`)
- [x] Verify COGS is negated on reversal (P&L restored) and fund balance stays unchanged
- [x] Verify the one-step `quick_consume` view reuses `ConsumptionOperation.create(...)` and enforces officer/ownership/nature/availability/unit guards
- [x] UI: stock detail `live` tab renders the quick-consume form; Stock History shows the OUT movement; CONSUMED products leave `live`
- [x] Complete test suite covering all branches; each test has a small number of assertions (one behavior per test)
- [ ] Add a consumption-focused test pinning VR4 (reversal dependency guard: consumed product moved again in a later non-reversed outbound op)
- [ ] Pin the shared-engine branches (VC1–VC15, VC18–VC20, VR1–VR3, VR5, VR6) with consumption-specific focused tests where missing
- [ ] Register remaining operation specs under the same contract structure (see [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md))
