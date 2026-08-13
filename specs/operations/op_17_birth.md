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
| Operation type | `OperationType.BIRTH` (`"BIRTH"`) | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:21) |
| Proxy class | `BirthOperation` | [`op_birth.py`](../../apps/app_operation/models/proxies/op_birth.py:7) |
| URL slug | `"birth"` | [`op_birth.py`](../../apps/app_operation/models/proxies/op_birth.py:21) |
| Label | `"Birth"` | [`op_birth.py`](../../apps/app_operation/models/proxies/op_birth.py:22) |
| Theme | `danger` / `bi-box-arrow-up-right` (inherited default) | [`operation.py`](../../apps/app_operation/models/operation.py:112) |
| Source role | `system` | [`op_birth.py`](../../apps/app_operation/models/proxies/op_birth.py:23) |
| Destination role | `url` (must be a Project) | [`op_birth.py`](../../apps/app_operation/models/proxies/op_birth.py:24) |
| Registered in | `PROXY_MAP` | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:38) |
| Cross-op reference | row BI | [`operations-comparison.md`](operations-comparison.md) |

**Configuration flags** (all on [`op_birth.py`](../../apps/app_operation/models/proxies/op_birth.py:7)):

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
| Proxy class + type-specific config + `clean_source`/`clean_destination` + payment funds | [`op_birth.py`](../../apps/app_operation/models/proxies/op_birth.py:7) |
| Proxy registry / URL→class resolution | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:26) |
| Shared `Operation` engine (`clean`, `save`, `reverse`, `create`, `resolve_request`, `save_inventory`, `_auto_create_inventory_movements`, period assignment, reversable tx types) | [`operation.py`](../../apps/app_operation/models/operation.py:34) |
| Operation type enum | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:21) |

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
| `BIRTH_ISSUANCE` (system → project, no balance) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:284), entity map [:545](../../apps/app_transaction/transaction_type.py:545), op map [:629](../../apps/app_transaction/transaction_type.py:629), issuance set [:475](../../apps/app_transaction/transaction_type.py:475) |
| `BIRTH_PAYMENT` (system → project, **non-cash — excluded from `payment_types()`**) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:291), entity map [:546](../../apps/app_transaction/transaction_type.py:546), op map [:630](../../apps/app_transaction/transaction_type.py:630), payment set (excluded) [:417](../../apps/app_transaction/transaction_type.py:417) |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Balance derivation (payment types only — `BIRTH_PAYMENT` excluded, so a birth never moves a fund balance) | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) |
| Virtual/system-entity payment exemption | [`Entity.can_pay`](../../apps/app_entity/models/__init__.py:704) |
| Open financial period auto-created on entity creation | [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) |

### 2.5 Inventory layer (birth-specific)

| Concern | Implementing code |
|---------|-------------------|
| Giving-birth template gating: ANIMAL nature only; `gives_birth_to` FK; FEMALE/MIXED gender; `clean()` enforcement | [`models.py`](../../apps/app_inventory/models.py:148), `gives_birth_to` [:114](../../apps/app_inventory/models.py:114), `clean` [:181](../../apps/app_inventory/models.py:181), `accepts_operation` [:161](../../apps/app_inventory/models.py:161) |
| Newborn template defaults to mother's `gives_birth_to`; mother picker restricted to ACTIVE female/mixed project animals | [`forms.py`](../../apps/app_inventory/forms.py:192) (birth fields [:204](../../apps/app_inventory/forms.py:204), default newborn [:241](../../apps/app_inventory/forms.py:241)) |
| Lazy product creation per head (gender / birth_date / mother forwarded via transient attrs) | [`operation.py`](../../apps/app_operation/models/operation.py:916) (`_auto_create_inventory_movements`) |
| Auto inbound movement lines + `Product` creation, status ACTIVE | [`operation.py`](../../apps/app_operation/models/operation.py:867), [`models.py`](../../apps/app_inventory/models.py:533) (`Product.status` [:613](../../apps/app_inventory/models.py:613)) |
| Identity: `INDIVIDUAL` tracking requires a unique tag per entity | [`Product.Meta`](../../apps/app_inventory/models.py:952) (`UniqueConstraint(entity, unique_id)`), `next_tag` [:233](../../apps/app_inventory/models.py:233) |
| Movement-based valuation (`movement_state`, `inventory_value`) — born value carried **once** in inventory | [`stock.py`](../../apps/app_inventory/stock.py:111), `inventory_value` [:143](../../apps/app_inventory/stock.py:143), `_INBOUND_TYPES` [:13](../../apps/app_inventory/stock.py:13) |

### 2.6 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (dedicated Birth) | [`BirthCreateView`](../../apps/app_operation/views/create_operation/create_birth_view.py:9) |
| POST parsing/validation | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) |
| Reverse view (reason required) | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) |
| Detail view (transactions + reversal button) | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) |
| URL: `/<pk>/birth/create` | [`urls.py`](../../apps/app_operation/urls.py:36) |
| URL: `/<pk>/reverse/` | [`urls.py`](../../apps/app_operation/urls.py:192) |
| URL: `/<pk>/detail/` | [`urls.py`](../../apps/app_operation/urls.py:182) |
| Templates | [`birth_form.html`](../../apps/app_operation/templates/app_operation/birth_form.html), [`reverse_form.html`](../../apps/app_operation/templates/app_operation/reverse_form.html), [`operation_detail.html`](../../apps/app_operation/templates/app_operation/operation_detail.html), entry link in [`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html) |

### 2.7 Tests

| Concern | Test file |
|---------|-----------|
| Create branches (validation, issuance + payment, auto inbound movement, lazy product creation, ACTIVE status, ledger) | [`test_birth_birth_create.py`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py) |
| Reverse branches (reversal record, counter-tx, auto lines reversed, negated ledger, born products REMOVED) | [`test_birth_birth_reversal.py`](../../apps/app_operation/tests/operations/birth/test_birth_birth_reversal.py) |
| Newborn animal attributes (mother / gender / birth_date / `gives_birth_to` default) | [`test_birth_animal_attributes.py`](../../apps/app_operation/tests/operations/birth/test_birth_animal_attributes.py) |
| Coverage manifest (executable branch registry) | [`tests/base.py`](../../apps/app_operation/tests/base.py:670) |

---

## 3. Money flow & entities

- **Source (payer):** the single **System** entity (`is_system=True`). Virtual — never balance-checked, exempt from fund-balance validation (`payment_source_fund`).
- **Destination (receiver):** the **Project** entity in the URL (`is_project=True`). Its fund is the target fund; the newborn assets belong to this project.
- **Transaction flow** (both on create, system → project):

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `BIRTH_ISSUANCE` | `system.fund → project.fund` | none (issuance, not a payment type) |
| 2 | `BIRTH_PAYMENT` | `system.fund → project.fund` | **none** — non-cash bookkeeping, **excluded from `payment_types()`** |

- **Payment source fund:** `self.source` (system) — [`op_birth.py`](../../apps/app_operation/models/proxies/op_birth.py:40)
- **Payment target fund:** `self.destination` (project) — [`op_birth.py`](../../apps/app_operation/models/proxies/op_birth.py:44)

> **No cash flow.** The born animal's value is carried **exactly once**, in movement-based inventory value ([`inventory_value()`](../../apps/app_inventory/stock.py:143)). It **never** appears in the project's fund balance (`BIRTH_PAYMENT` is non-cash — not in `payment_types()`, so no balance/payable/receivable effect) and is **not** recognized in `profit_loss` at birth (capitalized as an asset, not income).

---

## 4. Settlement model

Derived from [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:242) using payment-type transactions only (note: `BIRTH_PAYMENT` is **not** a payment type for balance purposes, but it *is* the one-shot settlement transaction for this operation):

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
| VC1 | Source is System | `source.is_system` | `ValidationError` | `"Birth source must be the System entity."` | [`clean_source`](../../apps/app_operation/models/proxies/op_birth.py:48) | [`test_source_must_be_system_entity`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:146), [`test_source_person_entity_raises_validation_error`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:153) |
| VC2 | Destination is Project | `destination.is_project` | `ValidationError` | `"Birth destination must be a Project entity."` | [`clean_destination`](../../apps/app_operation/models/proxies/op_birth.py:52) | [`test_destination_must_be_project_entity`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:164), [`test_destination_world_entity_raises_validation_error`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:171) |
| VC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | shared engine suite (cf. [`op_1`](op_1_cash_injection.md) VC3) |
| VC4 | Destination entity active | `destination.active` | `ValidationError` | same as VC3 | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | shared engine suite |
| VC5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | [`SourceFundMixin`](../../apps/app_base/mixins.py:132) | shared engine suite |
| VC6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | [`TargetFundMixin`](../../apps/app_base/mixins.py:152) | shared engine suite |
| VC7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | [`AmountCleanMixin`](../../apps/app_base/mixins.py:69) | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:182), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:195) |
| VC8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:81) | [`test_officer_must_be_a_staff_user`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:212) |
| VC9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:84) | [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:221) |
| VC10 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:541) | period suite |
| VC11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) | period suite |
| VC12 | Balance exempt (system payer) | no balance check | never fails | — | `check_balance_on_payment=False` | [`test_check_balance_on_payment_is_disabled`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:97) |
| VC13 | Tx entity-type contract | `source.is_system` and `target.is_project` | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | [`Transaction.create()`](../../apps/app_transaction/models.py:144) + map [:545](../../apps/app_transaction/transaction_type.py:545) | implied by VC1/VC2 (model clean blocks first) |
| VC14 | Tx operation-type allowed | document is `BIRTH` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | [`Transaction.create()`](../../apps/app_transaction/models.py:155) + map [:629](../../apps/app_transaction/transaction_type.py:629) | implied by VC1/VC2 |
| VC15 | Source ≠ target | system ≠ project | always true | `"Source and target funds must be different."` | [`Transaction.clean()`](../../apps/app_transaction/models.py:107) | structural (system ≠ project) |
| VC16 | Template is a giving-birth (or newborn) ANIMAL | template `nature == ANIMAL` (BIRTH allowed) | `ValidationError` | template rejected by `accepts_operation(BIRTH)` | [`ProductTemplate.accepts_operation`](../../apps/app_inventory/models.py:161) | [`test_animal_attributes.py`](../../apps/app_inventory/tests/test_animal_attributes.py) (nature gating) |
| VC17 | Mother is an ACTIVE female/mixed animal of the project (when a mother is picked) | mother in restricted queryset | form `ValidationError` | mother picker restricted | [`InvoiceItemCreateForm`](../../apps/app_inventory/forms.py:204) | [`test_birth_sets_gender_birth_date_and_mother`](../../apps/app_operation/tests/operations/birth/test_birth_animal_attributes.py:90) |
| VC18 | Newborn template present | `product_template` chosen (defaults to mother's `gives_birth_to`) | form `ValidationError` | `"Newborn template is required (or select a mother whose template has a 'gives birth to' template)."` | [`InvoiceItemCreateForm.clean()`](../../apps/app_inventory/forms.py:241) | [`test_birth_defaults_newborn_template_to_gives_birth_to`](../../apps/app_operation/tests/operations/birth/test_birth_animal_attributes.py:99) |
| VC19 | Identity — unique tag per entity | `INDIVIDUAL` tracking: `unique_id` present + unique per `(entity, unique_id)` | `ValidationError` / `IntegrityError` | DB `UniqueConstraint` | [`Product.Meta`](../../apps/app_inventory/models.py:952) | [`test_movement_lines_have_lazily_created_tagged_products`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:245) |
| VC20 | Unit consistency | quantity is a multiple of `product_template.minimum_quantity` | `ValidationError` | unit-step error | inventory form / movement clean | shared inventory suite |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | 1 × `BIRTH_ISSUANCE`, amount `== op.amount`, `system → project` | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:222) | [`test_save_creates_issuance_and_payment_transactions`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:108) |
| SC2 | Payment tx created (non-cash) | 1 × `BIRTH_PAYMENT`, amount `== op.amount`, `system → project`; **not** a `payment_types()` type → no balance/payable/receivable effect | [`LinkedPaymentTransactionMixin.save()`](../../apps/app_base/mixins.py:424) | same as SC1 |
| SC3 | Tx amounts equal op amount | both txs `amount == op.amount` | transaction creation | [`test_transaction_amounts_match_operation`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:129) |
| SC4 | Tx fund direction | both txs `source=system`, `target=project` | [`op_birth.py`](../../apps/app_operation/models/proxies/op_birth.py:40) | [`test_transaction_direction_is_system_to_project`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:122) |
| SC5 | Fully settled immediately | `amount_settled == amount`, `remaining == 0`, `is_fully_settled` | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:268) | [`test_is_fully_settled_after_creation`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:135) |
| SC6 | No cash flow | project fund balance unchanged (payment non-cash); system (virtual) ▼ in bookkeeping only | `payment_types()` exclusion + `Entity.balance_at` | differential invariant (cf. `test_create_then_reverse_leaves_world_unchanged` pattern) |
| SC7 | Auto inbound movement lines | `INDIVIDUAL` → one line per head (qty 1, shared `group_key`); `COMMODITY` → one line at item qty | [`_auto_create_inventory_movements`](../../apps/app_operation/models/operation.py:867) | [`test_create_auto_creates_inbound_movement_lines`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:232) |
| SC8 | Lazy product creation | each head lazy-creates its own tagged `Product` (qty 1, unique tag) | [`operation.py`](../../apps/app_operation/models/operation.py:916) + `Product` lazy-create | [`test_movement_lines_have_lazily_created_tagged_products`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:245) |
| SC9 | Newborn status ACTIVE | each created product `status == ACTIVE` | [`Product.status`](../../apps/app_inventory/models.py:613) | [`test_created_product_is_active`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:259) |
| SC10 | Newborn attributes recorded | `gender`, `birth_date`, `mother` set on the newborn | birth flow `birth_attrs` in [`operation.py`](../../apps/app_operation/models/operation.py:924) | [`test_birth_sets_gender_birth_date_and_mother`](../../apps/app_operation/tests/operations/birth/test_birth_animal_attributes.py:90), [`test_birth_male_gender_recorded`](../../apps/app_operation/tests/operations/birth/test_birth_animal_attributes.py:105) |
| SC11 | Newborn template defaulted | newborn `product_template == mother.gives_birth_to` unless overridden | [`InvoiceItemCreateForm.clean()`](../../apps/app_inventory/forms.py:241) | [`test_birth_defaults_newborn_template_to_gives_birth_to`](../../apps/app_operation/tests/operations/birth/test_birth_animal_attributes.py:99) |
| SC12 | Inventory value increases once | `movement_state(product)` → `qty > 0`, `value = qty × carried cost`; `inventory_value()` includes the born value; `FinancialPeriod.end_assets` ▲ once (via inventory, not cash) | [`movement_state`](../../apps/app_inventory/stock.py:111) + [`inventory_value`](../../apps/app_inventory/stock.py:143) | [`test_create_writes_movement_and_issuance_ledger_entries`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:272) |
| SC13 | Period auto-assigned | `period` = the project's covering period (open period auto-created at entity creation) | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) + [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) | covered by period suite |

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:34) | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/birth/test_birth_birth_reversal.py:196) |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:47) | [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/birth/test_birth_birth_reversal.py:204) |
| VR3 | No explicit txs to reverse | all txs are implicit (one-shot issuance + payment) | `ValidationError` (would require manual reversal) | `"You can't reverse this object as it has non-reversed transactions…"` | [`ReversableModel._requires_transaction_reversal`](../../apps/app_base/models.py:203) + [`Operation._implicit_reversable_transaction_types`](../../apps/app_operation/models/operation.py:478) | implied by successful reverse ([`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/birth/test_birth_birth_reversal.py:90)) |
| VR4 | No non-reversed adjustments | n/a — Birth is not adjustable | never fails | — | `is_adjustable=False` | n/a |
| VR5 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:82) | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:235) | [`test_reverse_creates_reversal_record`](../../apps/app_operation/tests/operations/birth/test_birth_birth_reversal.py:74) |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:270) | [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/birth/test_birth_birth_reversal.py:82) |
| SR3 | Reversal inherits identity | `amount`, `source`, `destination` copied | [`ReversableModel._get_reverse_kwargs`](../../apps/app_base/models.py:184) | structural (same engine as [`op_1`](op_1_cash_injection.md) SR3) |
| SR4 | Counter-tx for issuance | `project → system`, same amount, same type, `reversal_of=original` | [`Transaction.reverse()`](../../apps/app_transaction/models.py:206) | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/birth/test_birth_birth_reversal.py:90) |
| SR5 | Counter-tx for payment | `project → system`, same amount, same type, `reversal_of=original` | same as SR4 | same as SR4 |
| SR6 | Counter-txs preserve type + amount | `counter.type == original.type`, `counter.amount == original.amount` | same as SR4 | same as SR4 |
| SR7 | Auto movement lines reversed | one reversal line per original (equal qty, `reversal_of` link); originals preserved | [`Operation.reverse()`](../../apps/app_operation/models/operation.py:1070) → `line.reverse()` | [`test_reverse_reverses_auto_movement_lines`](../../apps/app_operation/tests/operations/birth/test_birth_birth_reversal.py:107), [`test_reverse_movement_ledger_negation_exact_set`](../../apps/app_operation/tests/operations/birth/test_birth_birth_reversal.py:140) |
| SR8 | Ledger negated | each born product's net presence → `qty 0`, `value 0` | [`movement_state`](../../apps/app_inventory/stock.py:111) | [`test_reverse_negates_ledger_entries`](../../apps/app_operation/tests/operations/birth/test_birth_birth_reversal.py:127) |
| SR9 | Born products removed from stock | products persist (audit trail) but `status == REMOVED`; `validate_active()` fails → barred from new operations; value leaves `inventory_value()` | [`Product.status`](../../apps/app_inventory/models.py:613) + [`validate_active`](../../apps/app_inventory/models.py:760) | [`test_reverse_born_products_removed_from_stock`](../../apps/app_operation/tests/operations/birth/test_birth_birth_reversal.py:171) |
| SR10 | Reversal op owns no txs | `reversal.get_all_transactions().count() == 0` (save skips tx creation for reversals) | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:226) | shared engine (cf. [`op_1`](op_1_cash_injection.md) SR7) |
| SR11 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger, inventory value) | whole engine | shared engine invariant |

### 5.3 `pay` (one-shot guard)

There is **no standalone pay action** for Birth:

| Branch | Behavior | Enforced by | Pinned by test |
|--------|----------|-------------|----------------|
| `process_payment()` called | no-op (returns immediately — `can_pay=False`) | [`process_payment`](../../apps/app_operation/models/operation.py:686) | n/a (covered by `can_pay=False`) |
| `create_payment_transaction()` called after create | `ValidationError` — one-shot allows a single payment only, amount must equal `op.amount` | [`create_payment_transaction`](../../apps/app_base/mixins.py:391) | [`test_one_shot_prevents_second_payment`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:288) |

### 5.4 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by [`ImmutableMixin`](../../apps/app_base/mixins.py:30) via `_immutable_fields` ([`operation.py`](../../apps/app_operation/models/operation.py:51)). Shared with every operation (see [`op_1`](op_1_cash_injection.md) §5.4).

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — [`Entity.save()`](../../apps/app_entity/models/__init__.py:714).
- The operation's governing entity (`period_entity`) is the **destination project** (`_dest_role = "url"`) — [`Operation.period_entity`](../../apps/app_operation/models/operation.py:491). The System (virtual) has no periods and is exempt.
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC11).
- New operations dated inside a **closed** period are rejected (VC10).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period ([`_reverse_period`](../../apps/app_operation/models/operation.py:455)).

---

## 7. Entity roles & balance contract

- System is the only allowed source; Project the only allowed destination — enforced at model (VC1/VC2) and transaction (VC13) layers.
- `BIRTH_PAYMENT` is **deliberately excluded** from `payment_types()` ([`transaction_type.py`](../../apps/app_transaction/transaction_type.py:417)) — it is a non-cash bookkeeping record. The project's fund balance, payables and receivables are **never** affected by a birth.
- The born asset's value is carried **exactly once** in movement-based inventory value ([`inventory_value()`](../../apps/app_inventory/stock.py:143)); `FinancialPeriod.end_assets` = cash + movement-based inventory + loans + advances, so a birth increases `end_assets` exactly once, via inventory.
- System is **virtual**: `can_pay` always returns `True`, so births are never blocked by fund balance (VC12).

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Create route | `POST/GET /<project_pk>/birth/create` → [`BirthCreateView`](../../apps/app_operation/views/create_operation/create_birth_view.py:9) |
| Source selection | locked to the single **System** entity (`_source_role="system"`); no picker |
| Destination selection | the **Project** from the URL (`_dest_role="url"`); [`get_related_entities`](../../apps/app_operation/models/operation.py:440) returns `[]` → no secondary-entity field |
| Category | hidden (no category) |
| Amount | computed from item totals; raw `amount` POST field validated > 0 at model |
| Invoice items | `InvoiceItemCreateFormSet` with `is_birth=True` — newborn `product_template`, `quantity`, `unit_price`, plus birth-only fields `mother`, `gender`, `birth_date` |
| Giving-birth product | the **mother** picker lists only **ACTIVE FEMALE/MIXED** animals owned by the project (template `gender`/`gives_birth_to`); a template "can give birth" when `nature=ANIMAL`, `gender ∈ {FEMALE, MIXED}` and `gives_birth_to` is set ([`ProductTemplate.clean`](../../apps/app_inventory/models.py:181)) |
| Born product type | the newborn `product_template` defaults to the mother's `gives_birth_to` (e.g. Dairy Cow → Calf); the user may override with any ANIMAL template selectable for the project |
| POST parsing | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) — date format, description, category (n/a), `amount_paid` (n/a, forced 0) |
| List entry | "Birth" link in [`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html) |
| Detail | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) — shows both transactions + auto movement lines + settlement + reversal button |
| Reverse | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

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
| Config flags | [`test_has_category_config_is_false`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:82), [`test_category_required_config_is_false`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:85), [`test_can_pay_config_is_false`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:88), [`test_is_one_shot_operation_config_is_true`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:91), [`test_is_partially_payable_config_is_false`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:94), [`test_check_balance_on_payment_is_disabled`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:97), [`test_creates_assets_config_is_true`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:101) | flags |
| Tx creation + counts | [`test_save_creates_issuance_and_payment_transactions`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:108) | SC1, SC2 |
| Tx direction | [`test_transaction_direction_is_system_to_project`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:122) | SC4 |
| Tx amounts | [`test_transaction_amounts_match_operation`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:129) | SC3 |
| Settlement | [`test_is_fully_settled_after_creation`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:135) | SC5 |
| Source validation | [`test_source_must_be_system_entity`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:146), [`test_source_person_entity_raises_validation_error`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:153) | VC1 |
| Destination validation | [`test_destination_must_be_project_entity`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:164), [`test_destination_world_entity_raises_validation_error`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:171) | VC2 |
| Amount | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:182), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:195) | VC7 |
| Officer | [`test_officer_must_be_a_staff_user`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:212), [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:221) | VC8, VC9 |
| Auto inbound lines | [`test_create_auto_creates_inbound_movement_lines`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:232) | SC7 |
| Lazy tagged products | [`test_movement_lines_have_lazily_created_tagged_products`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:245) | SC8, VC19 |
| ACTIVE status | [`test_created_product_is_active`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:259) | SC9 |
| Ledger / movement state | [`test_create_writes_movement_and_issuance_ledger_entries`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:272) | SC12 |
| One-shot guard | [`test_one_shot_prevents_second_payment`](../../apps/app_operation/tests/operations/birth/test_birth_birth_create.py:288) | BP2 |
| Newborn attributes | [`test_birth_sets_gender_birth_date_and_mother`](../../apps/app_operation/tests/operations/birth/test_birth_animal_attributes.py:90), [`test_birth_male_gender_recorded`](../../apps/app_operation/tests/operations/birth/test_birth_animal_attributes.py:105) | SC10 |
| Newborn template default | [`test_birth_defaults_newborn_template_to_gives_birth_to`](../../apps/app_operation/tests/operations/birth/test_birth_animal_attributes.py:99) | SC11, VC18 |
| Reverse happy path | [`test_reverse_creates_reversal_record`](../../apps/app_operation/tests/operations/birth/test_birth_birth_reversal.py:74), [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/birth/test_birth_birth_reversal.py:82) | SR1, SR2 |
| Counter txs | [`test_reverse_creates_counter_transactions`](../../apps/app_operation/tests/operations/birth/test_birth_birth_reversal.py:90) | SR4–SR6 |
| Auto lines reversed | [`test_reverse_reverses_auto_movement_lines`](../../apps/app_operation/tests/operations/birth/test_birth_birth_reversal.py:107), [`test_reverse_movement_ledger_negation_exact_set`](../../apps/app_operation/tests/operations/birth/test_birth_birth_reversal.py:140) | SR7, SR8 |
| Born products removed | [`test_reverse_born_products_removed_from_stock`](../../apps/app_operation/tests/operations/birth/test_birth_birth_reversal.py:171) | SR9 |
| Reverse constraints | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/birth/test_birth_birth_reversal.py:196), [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/birth/test_birth_birth_reversal.py:204) | VR1, VR2 |
| Reversed-birth stock removal | [`test_status_removed_after_reversed_birth`](../../apps/app_inventory/tests/test_product.py:219), [`test_reversed_birth_product_not_in_live_stock`](../../apps/app_inventory/tests/test_views_get_stock_detail_view.py:159) | SR9 |

---

## 11. Tasks

- [x] Verify `BIRTH_ISSUANCE` + `BIRTH_PAYMENT` created on save (non-cash payment)
- [x] Verify transaction fund direction: `system.fund → project.fund` for both
- [x] Verify operation is fully settled immediately
- [x] Verify `BIRTH_PAYMENT` is excluded from `payment_types()` → no balance / payable / receivable effect
- [x] Verify all validation branches VC1–VC20 (VC16–VC20 inventory/giving-birth rules)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify `create_payment_transaction()` is blocked after creation (one-shot)
- [x] Verify auto inbound movement lines (one per head for `INDIVIDUAL`) with lazy tagged products
- [x] Verify newborn status ACTIVE and animal attributes (gender / birth_date / mother)
- [x] Verify newborn template defaults to mother's `gives_birth_to` (Dairy Cow → Calf)
- [x] Verify reversal creates counter-transactions `project.fund → system.fund` and reverses auto lines
- [x] Verify born products become REMOVED on reversal (out of stock, barred from new operations)
- [x] Verify inventory value increases once at create and returns to baseline on reverse
- [x] UI: create form — mother picker (ACTIVE female/mixed project animals), newborn template selection, birth-only fields
- [x] Complete test suite covering all branches; each test has a small number of assertions (one behavior per test)
- [ ] Pin VC20 (unit multiple) and the shared-engine branches (VC3–VC6, VC10, VC11, VR5) with birth-specific focused tests where missing
