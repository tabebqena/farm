# Birth — Operation Contract

**Epic:** Inventory / Livestock — One-Shot (stock event)
**Type:** Stock event (no accounting transactions), creates assets (`creates_assets=True`, `has_invoice=True`)
**Actions:** `create`, `move items` (auto), `reverse`
**Contract status:** v3 — Birth is a **stock event**, not an accounting operation: it creates **no** `Transaction` rows, has no payment/settlement/repayment/adjustment machinery, and is still assigned to a financial period (and blocked inside a closed one).

> **Primary source of contract.** This document is the authoritative contract for the **Birth** operation.
> Every clause below names its implementing code (model → mixin → transaction → view) and its pinning test — as plain names, never links, so renames do not break the spec.
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
| `can_pay` | `False` | no payment action |
| `is_partially_payable` | `False` | n/a (no settlement) |
| `check_balance_on_payment` | `False` | n/a (no payment) |
| `has_category` / `category_required` | `False` | no financial category |
| `has_repayment` | `False` | no repayment action |
| `has_invoice` | `True` | invoice items + auto inventory movements |
| `creates_assets` | `True` | new assets are created (lazy products) |
| `can_create_movement` | `False` | no manual movement screen — the `can_create_movement` property is `True` only for PURCHASE/SALE; birth's inbound movements are auto-created via `save_inventory()` → `_auto_create_inventory_movements()` |

> **No accounting mixins.** `BirthOperation` inherits only `ImmutableMixin`, `AmountCleanMixin`,
> `OfficerMixin`, `ReversableModel`, `BaseModel` (via the lean `Operation` base). It does **not**
> inherit `LinkedIssuanceTransactionMixin`, `LinkedPaymentTransactionMixin`,
> `LinkedRePaymentTransactionMixin` or `AdjustableMixin` — so no transactions, no settlement,
> no repayment, no adjustments.

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row names the code that must honor it (plain names, no links).

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_source`/`clean_destination` | |
| Proxy registry / URL→class resolution | |
| Shared `Operation` engine (`clean`, `save`, `reverse`, `create`, `resolve_request`, `save_inventory`, `_auto_create_inventory_movements`, period assignment, reversable tx types) | |
| Operation type enum | |

### 2.2 Core engine (mixins / base)

| Concern | Implementing code |
|---------|-------------------|
| Immutability of `source`/`destination`/`amount`/`period` | `ImmutableMixin` + `_immutable_fields` |
| Amount must be > 0 | `AmountCleanMixin` |
| Officer must be staff + active | `OfficerMixin` |
| Reversal mechanics (clone, `reversal_of`, guards) | `ReversableModel` + `Operation.reverse()` |
| Effective amount == amount (not adjustable) | `Operation.effective_amount` (base fallback) |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| **None** — Birth creates no `Transaction` rows | (no transaction mixins inherited) |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Fund balance never affected (no payment) | `Entity.balance_at` (no Birth tx types are payment types) |
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
| Reversal dependency guard — born products must still be ACTIVE to reverse the birth | `Operation.reverse()` |

### 2.6 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (dedicated Birth) | `BirthCreateView` |
| POST parsing/validation | `OperationDataValidator` |
| Reverse view (reason required) | `operation_reverse_view` |
| Detail view (aggregate amount + movement lines + reversal action; no payment UI) | `operation_detail_view` |
| URL: `/<pk>/birth/create` | |
| URL: `/<pk>/reverse/` | |
| URL: `/<pk>/detail/` | |
| Templates | |

### 2.7 Tests

| Concern | Test file |
|---------|-----------|
| Create branches (validation, no transactions, auto inbound movement, lazy product creation, ACTIVE status, period assigned) | |
| Reverse branches (reversal record, no counter-tx, auto lines reversed, negated ledger, born products REMOVED) | |
| Newborn animal attributes (mother / gender / birth_date / `gives_birth_to` default) | |
| Coverage manifest (executable branch registry) | |

---

## 3. Money flow & entities

- **Source (role):** the single **System** entity (`is_system=True`). Virtual.
- **Destination (role):** the **Project** entity in the URL (`is_project=True`). The newborn assets belong to this project.
- **No transactions are created.** The born animal's value is carried **exactly once**, in
  movement-based inventory value (`inventory_value()`). It never appears in the project's fund
  balance and is not recognized in `profit_loss` (capitalized as an asset, not income).

---

## 4. Settlement model

There is **no settlement model** — Birth does not inherit the payment/settlement machinery.
`amount_settled`, `is_fully_settled`, `amount_remaining_to_settle`, `payment_transactions` do
**not** exist on a `BirthOperation`. The operation's value lives in inventory.

---

## 5. Actions

### 5.1 `create`

Entry points: model `BirthOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → then the invoice formset → `save_inventory()` → `_auto_create_inventory_movements()`.

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source is System | `source.is_system` | `ValidationError` | `"Birth source must be the System entity."` | `clean_source` | |
| VC2 | Destination is Project | `destination.is_project` | `ValidationError` | `"Birth destination must be a Project entity."` | `clean_destination` | |
| VC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | `Operation.clean()` | shared engine suite |
| VC4 | Destination entity active | `destination.active` | `ValidationError` | same as VC3 | `Operation.clean()` | shared engine suite |
| VC5 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | `AmountCleanMixin` | |
| VC6 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | `OfficerMixin` | |
| VC7 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | `OfficerMixin` | |
| VC8 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | `Operation.clean()` | period suite |
| VC9 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | `Operation.save()` | period suite |
| VC10 | Template is a giving-birth (or newborn) ANIMAL | template `nature == ANIMAL` (BIRTH allowed) | `ValidationError` | template rejected by `accepts_operation(BIRTH)` | `ProductTemplate.accepts_operation` | `test_non_animal_template_rejected_for_birth` |
| VC11 | Mother is an ACTIVE female/mixed animal of the project (when a mother is picked) | mother in restricted queryset | form `ValidationError` | mother picker restricted | `InvoiceItemCreateForm` | |
| VC12 | Newborn template present | `product_template` chosen (defaults to mother's `gives_birth_to`) | form `ValidationError` | `"Newborn template is required (or select a mother whose template has a 'gives birth to' template)."` | `InvoiceItemCreateForm.clean()` | `test_newborn_template_required_without_gives_birth_to` |
| VC13 | Identity — unique tag per entity | `INDIVIDUAL` tracking: `unique_id` present + unique per `(entity, unique_id)` | `ValidationError` / `IntegrityError` | DB `UniqueConstraint` | `Product.Meta` | |
| VC14 | Unit consistency | quantity is a multiple of `product_template.minimum_quantity` | `ValidationError` | unit-step error | inventory form / movement clean | shared inventory suite |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | No transactions created | `get_all_transactions().count() == 0` (no issuance, no payment) | (no transaction mixins) | |
| SC2 | No settlement machinery | `amount_settled`/`is_fully_settled`/`create_payment_transaction` absent | (no payment mixin) | |
| SC3 | Auto inbound movement lines | `INDIVIDUAL` → one line per head (qty 1, shared `group_key`); `COMMODITY` → one line at item qty | `_auto_create_inventory_movements` | |
| SC4 | Lazy product creation | each head lazy-creates its own tagged `Product` (qty 1, unique tag) | + `Product` lazy-create | |
| SC5 | Newborn status ACTIVE | each created product `status == ACTIVE` | `Product.status` | |
| SC6 | Newborn attributes recorded | `gender`, `birth_date`, `mother` set on the newborn | birth flow `birth_attrs` | |
| SC7 | Newborn template defaulted | newborn `product_template == mother.gives_birth_to` unless overridden | `InvoiceItemCreateForm.clean()` | |
| SC8 | Inventory value increases once | `movement_state(product)` → `qty > 0`, `value = qty × carried cost`; `inventory_value()` includes the born value; `FinancialPeriod.end_assets` ▲ once (via inventory, not cash) | `movement_state` + `inventory_value` | |
| SC9 | Period auto-assigned | `period` = the project's covering period (open period auto-created at entity creation) | `Operation.save()` + `Entity.save()` | covered by period suite |
| SC10 | Fund balance unchanged | `balance_at()` unaffected (no payment) | `Entity.balance_at` | `test_project_fund_unchanged_by_birth` |

### 5.2 `reverse`

Entry points: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | `ReversableModel._validate_can_be_reversed` + view guard | |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | `ReversableModel._validate_can_be_reversed` + view guard | |
| VR3 | No non-reversed adjustments | n/a — Birth is not adjustable | never fails | — | `is_adjustable=False` | n/a |
| VR4 | Born products still ACTIVE | every born product's `status == ACTIVE` — none was moved again in a later non-reversed outbound op (SALE/DEATH/CONSUMPTION) | `ValidationError` | `"Cannot reverse this operation: its products were moved again in a later operation."` | `Operation.reverse()` (shared reversal dependency guard, extended to cover BIRTH) | `test_reversal_blocked_when_born_product_moved_again_in_later_death` — the reverse of a birth is valid only while the newborn is still ACTIVE in stock; once it has been sold/dead/consumed in a later operation the reversal would push the newborn's net presence negative, so the guard blocks it |
| VR5 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | `operation_reverse_view` | view contract (see §8) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | `ReversableModel.reverse()` | |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | `ReversableModel.reverse()` | |
| SR3 | Reversal inherits identity | `amount`, `source`, `destination` copied | `ReversableModel._get_reverse_kwargs` | structural (same engine as [`op_1`](op_1_cash_injection.md) SR3) |
| SR4 | No counter-transactions | neither the original nor its reversal owns any `Transaction` | (no transaction mixins) | |
| SR5 | Auto movement lines reversed | one reversal line per original (equal qty, `reversal_of` link); originals preserved | `Operation.reverse()` → `line.reverse()` | |
| SR6 | Ledger negated | each born product's net presence → `qty 0`, `value 0` | `movement_state` | |
| SR7 | Born products removed from stock | products persist (audit trail) but `status == REMOVED`; `validate_active()` fails → barred from new operations; value leaves `inventory_value()` | `Product.status` + `validate_active` | |
| SR8 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger, inventory value) | whole engine | `test_create_then_reverse_leaves_world_unchanged` |

### 5.3 `pay`

There is **no pay action** for Birth — it has no payment machinery at all (`create_payment_transaction`
does not exist on the class). Payment-related code is never reachable.

### 5.4 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by `ImmutableMixin` via `_immutable_fields`. Shared with every operation (see [`op_1`](op_1_cash_injection.md) §5.4).

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — `Entity.save()`.
- The operation's governing entity (`period_entity`) is the **destination project** (`_dest_role = "url"`) — `Operation.period_entity`. The System (virtual) has no periods and is exempt.
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC9).
- New operations dated inside a **closed** period are rejected (VC8).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period (`_reverse_period`).

---

## 7. Entity roles & balance contract

- System is the only allowed source; Project the only allowed destination — enforced at model (VC1/VC2).
- No transactions → the project's fund balance, payables and receivables are **never** affected by a birth.
- The born asset's value is carried **exactly once** in movement-based inventory value (`inventory_value()`); `FinancialPeriod.end_assets` = cash + movement-based inventory + loans + advances, so a birth increases `end_assets` exactly once, via inventory.

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
| Detail | `operation_detail_view` — shows the operation total + auto movement lines + reversal action; **no** payment/settlement sections (rendered as one-shot) |
| Reverse | `operation_reverse_view` — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source=system · VC2 dest=project · VC3 source active · VC4 dest active · VC5 amount>0 · VC6 officer staff · VC7 officer active · VC8 not closed-period · VC9 covering period exists · VC10 template is ANIMAL (giving-birth/newborn) · VC11 mother active female/mixed · VC12 newborn template present · VC13 unique tag per entity · VC14 unit multiple

**create — effects:** SC1 no transactions · SC2 no settlement machinery · SC3 auto inbound lines · SC4 lazy product creation · SC5 status ACTIVE · SC6 newborn attributes · SC7 newborn template defaulted · SC8 inventory value ▲ once · SC9 period assigned · SC10 fund balance unchanged

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no adjustments (n/a) · VR4 born products still ACTIVE · VR5 reason required (view)

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 identity copied · SR4 no counter-txs · SR5 auto lines reversed · SR6 ledger negated · SR7 born products REMOVED · SR8 differential invariant

**immutability:** IM1/IM2/IM3 source/destination/amount immutable

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| Config flags | `test_can_pay_config_is_false` · `test_is_partially_payable_config_is_false` · `test_check_balance_on_payment_is_disabled` · `test_has_category_config_is_false` · `test_category_required_config_is_false` · `test_has_repayment_config_is_false` · `test_has_invoice_config_is_true` · `test_creates_assets_config_is_true` · `test_can_create_movement_is_false` | flags |
| No transactions | `test_save_creates_no_transactions` | SC1 |
| No settlement machinery | `test_no_settlement_or_payment_machinery` | SC2 |
| Source validation | `test_source_must_be_system_entity` | VC1 |
| Destination validation | `test_destination_must_be_project_entity` | VC2 |
| Amount | `test_amount_zero_raises_validation_error` · `test_amount_negative_raises_validation_error` | VC5 |
| Officer | `test_officer_must_be_a_staff_user` · `test_officer_must_be_active` | VC6, VC7 |
| Template nature gating | `test_non_animal_template_rejected_for_birth` | VC10 |
| Mother picker (active female/mixed) | `test_mother_picker_only_lists_active_female_mixed` · `test_mother_must_be_active_form_error` · `test_mother_active_passes_form_validation` | VC11 |
| Newborn template required | `test_newborn_template_required_without_gives_birth_to` | VC12 |
| Auto inbound lines | `test_create_auto_creates_inbound_movement_lines` | SC3 |
| Lazy tagged products | `test_movement_lines_have_lazily_created_tagged_products` | SC4, VC13 |
| ACTIVE status | `test_created_product_is_active` | SC5 |
| Newborn attributes | `test_birth_sets_gender_birth_date_and_mother` · `test_birth_male_gender_recorded` · `test_birth_defaults_newborn_template_to_gives_birth_to` | SC6, SC7 |
| Ledger / movement state | `test_create_writes_movement_and_issuance_ledger_entries` | SC8 |
| Period assigned | `test_period_is_assigned_on_creation` | SC9 |
| Fund balance unchanged | `test_project_fund_unchanged_by_birth` | SC10 |
| Immutability | `test_source_is_immutable_after_save` · `test_destination_is_immutable_after_save` · `test_amount_is_immutable_after_save` | IM1–IM3 |
| Reversal — reversal record | `test_reverse_creates_reversal_record` · `test_reverse_marks_original_as_reversed` | SR1, SR2 |
| Reversal — no counter-txs | `test_reverse_creates_no_transactions` | SR4 |
| Reversal — lines reversed | `test_reverse_reverses_auto_movement_lines` · `test_reverse_movement_ledger_negation_exact_set` | SR5, SR6 |
| Reversal — born products REMOVED | `test_reverse_born_products_removed_from_stock` | SR7 |
| Reversal — constraints | `test_cannot_reverse_already_reversed_operation` · `test_cannot_reverse_a_reversal` | VR1, VR2 |
| Reversal — born products still ACTIVE | `test_reversal_blocked_when_born_product_moved_again_in_later_death` | VR4 |
| Reversal — reason required (view) | `test_reverse_view_rejects_missing_reason` · `test_reverse_view_with_reason_reverses_and_flows_reason` | VR5, SR10 |
| Differential invariant | `test_create_then_reverse_leaves_world_unchanged` | SR8 |
| View — create route | `test_get_birth_create_renders_birth_form` · `test_post_birth_create_creates_operation_with_movements` | §8 |
