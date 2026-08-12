# Plan: World Entity as Vendor & Client (with conditions)

## Goal

Allow the World entity to act as a **vendor** (purchase destination) and a **client** (sale source), subject to two safeguards:

1. **Fully paid** — an operation whose counterparty is the World must be paid in full (no partial payments, no lingering payable/receivable with the World).
2. **No standalone payment reversal** — the user can never reverse a World-involved payment transaction on its own. Reversal is only allowed at the **operation level**, which reverses issuance + payment + inventory movements together.

The World is **always available** as a selectable vendor/client option in the purchase/sale wizards for every project (no Stakeholder record required).

## Current state (why this is blocked today)

| Layer | File | Current behavior |
|---|---|---|
| Entity role flags | [`Entity.clean()`](apps/app_entity/models/__init__.py:326) | Force-resets `is_vendor`/`is_client` to `False` for virtual entities |
| Stakeholder | [`Stakeholder.clean()`](apps/app_entity/models/__init__.py:182) | Parent/target restricted to PERSON/PROJECT |
| Purchase | [`PurchaseOperation.clean_destination()`](apps/app_operation/models/proxies/op_purchase.py:75) | Requires `is_vendor` + active vendor Stakeholder |
| Sale | [`SaleOperation.clean_source()`](apps/app_operation/models/proxies/op_sale.py:60) | Requires `is_client` + active client Stakeholder |
| Transaction types | [`_TX_ENTITY_TYPE_MAP`](apps/app_transaction/transaction_type.py:497) | `PURCHASE_*` → `(is_project, is_vendor)`, `SALE_*` → `(is_client, is_project)` |
| Wizard selection | [`PurchaseWizardStep1Form`](apps/app_operation/forms.py:10), [`SaleWizardStep1Form`](apps/app_operation/forms.py:188) | Vendor/client queryset built only from Stakeholder relationships |
| Related entities | [`PurchaseOperation.get_related_entities()`](apps/app_operation/models/proxies/op_purchase.py:63), [`SaleOperation.get_related_entities()`](apps/app_operation/models/proxies/op_sale.py:75) | Returns only Stakeholder targets |
| Wizard guards | [`purchase_wizard.py`](apps/app_operation/views/create_operation/purchase_wizard.py:66), [`sale_wizard.py`](apps/app_operation/views/create_operation/sale_wizard.py:66) | Hard-block when the project has no vendors/clients |
| Standalone reversal | [`transaction_reverse_view()`](apps/app_transaction/views.py:370) | Currently allows reversing a single payment transaction |
| Operation reversal | [`_implicit_reversable_transaction_types`](apps/app_operation/models/operation.py:479) | Payment is NOT implicit for non-one-shot purchase/sale → op reversal requires payments reversed manually first |

## Design decisions (confirmed)

- **Reversal:** standalone transaction-level "reverse payment" is **blocked**; operation-level reversal remains fully available and reverses issuance + payment + movements together.
- **Availability:** World appears automatically as a vendor/client option in the wizards for every project (no Stakeholder record).

## Implementation steps

### 1. Helper: detect World counterparty

Add a helper so validation can branch on the World being the counterparty.

- Add property on `Operation` (e.g. `_counterparty_is_world`) returning:
  - `PURCHASE` → `self.destination.is_world`
  - `SALE` → `self.source.is_world`
  - otherwise `False`
- Used by clean methods, payment enforcement, and reversal logic.

### 2. Relax purchase/sale validation (allow World without a Stakeholder)

- `PurchaseOperation.clean_destination()`: if `self.destination.is_world`, skip the `is_vendor` + Stakeholder checks; otherwise keep existing behavior.
- `SaleOperation.clean_source()`: if `self.source.is_world`, skip the `is_client` + Stakeholder checks; otherwise keep existing behavior.
- Non-world behavior must remain identical (existing tests for non-vendor/non-client rejections must keep passing).

### 3. Transaction-type entity map

- In [`_build_tx_entity_type_map()`](apps/app_transaction/transaction_type.py:484), add predicates `is_vendor_or_world` and `is_client_or_world`.
- Use them for purchase/sale transaction types:
  - `PURCHASE_ISSUANCE`, `PURCHASE_PAYMENT`, `PURCHASE_ADJUSTMENT_INCREASE` → `(is_project, is_vendor_or_world)`
  - `PURCHASE_ADJUSTMENT_DECREASE` → `(is_vendor_or_world, is_project)`
  - `SALE_ISSUANCE`, `SALE_COLLECTION`, `SALE_ADJUSTMENT_INCREASE` → `(is_client_or_world, is_project)`
  - `SALE_ADJUSTMENT_DECREASE` → `(is_project, is_client_or_world)`
- This lets `Transaction.create()` (which enforces via `get_entity_type_violation`) accept World.

### 4. Expose World in the wizards

- `PurchaseWizardStep1Form` / `SaleWizardStep1Form`: include the World entity in the vendor/client queryset (union Stakeholder targets + World).
- `PurchaseOperation.get_related_entities()` / `SaleOperation.get_related_entities()`: append the World entity to the returned list.
- Relax the `_load_project` guards in `purchase_wizard.py` / `sale_wizard.py`: no longer hard-block when there are no Stakeholder vendors/clients (World is always available). Keep a warning only.
- `create_sale_view.post` prerequisite check relies on `get_related_entities`; with World appended it no longer blocks (verify).

### 5. Enforce "fully paid"

- In `Operation.process_payment()`: when `_counterparty_is_world`, require `amount_paid == self.amount` (reject partial / zero).
- In `LinkedPaymentTransactionMixin.create_payment_transaction()`: when the document is a World-involved purchase/sale, require `amount == amount_remaining_to_settle` (a later payment must fully settle).
- Optionally: wizard step-3 form validation that shows a clear message when the selected vendor/client is World and `amount_paid != total`.

### 6. Block standalone payment reversal (World-involved)

- `transaction_reverse_view()`: add a guard — if the transaction is a `PURCHASE_PAYMENT` / `SALE_COLLECTION` belonging to a World-involved purchase/sale, block with a message like *"This payment transaction involves the World entity and cannot be reversed alone. Reverse the entire operation instead."* (with audit + DebugContext, matching existing style).
- Transaction detail view: set `can_reverse = False` for these transactions so the button is hidden in [`transaction_detail.html`](apps/app_transaction/templates/app_transaction/transaction_detail.html:134).

### 7. Operation-level reversal reverses the payment implicitly

- Override `_implicit_reversable_transaction_types` on `PurchaseOperation` / `SaleOperation` (or on `Operation`) so that when `_counterparty_is_world`, the payment type is included.
- Effect: `_requires_transaction_reversal` returns `False` for a fully-paid World op → `ReversableModel.reverse()` proceeds and reverses issuance + payment automatically.
- `Operation.reverse()` inventory logic (movements must be reversed first, ledger negation) stays unchanged.

### 8. Tests

New tests:
- Purchase with World vendor succeeds and is fully paid.
- Sale with World client succeeds and is fully paid.
- Partial/zero payment on World-involved op rejected.
- Standalone reversal of World payment transaction rejected (view + `can_reverse`).
- Operation-level reversal of a fully-paid World purchase/sale reverses issuance + payment (world state unchanged).
- Wizard step 1 lists World as vendor/client; wizard guard no longer blocks when no Stakeholder vendors exist.
- Transaction type validator accepts World for purchase/sale.

Review/adjust existing tests:
- `apps/app_operation/tests/operations/purchase/*`, `sale/*` (validation, reversal).
- `apps/app_transaction/tests.py` (reversal tests — ensure the new guard only applies to World ops).
- `apps/app_operation/tests/wizard/*` (guard behavior).
- `apps/app_operation/tests/test_validators.py` (entity-type map).

### 9. Verification

- `python manage.py check`
- Targeted: `pytest apps/app_operation/tests/operations/purchase apps/app_operation/tests/operations/sale apps/app_transaction/tests.py`
- Full suite: `pytest -q`
- Update specs [`op_13_purchase.md`](specs/operations/op_13_purchase.md) / [`op_14_sale.md`](specs/operations/op_14_sale.md) to document the World-as-counterparty rule.

## Consequences

- The World becomes a supported external counterparty for purchase/sale; cash flows directly to/from the World entity.
- Because World ops are fully paid at creation, no perpetual payable/receivable is left on the World entity (its payables/receivables settle to zero).
- Payment transactions of World ops are protected from accidental single-transaction reversal; undoing requires a full operation reversal (audit path preserved).
- Purchase from World: project fund pays the World (project balance ↓). Sale to World: World pays the project (project balance ↑); `can_pay` returns `True` for virtual entities so no balance guard issue.

## Regression analysis

**Low-risk areas (additive):** Wizard querysets, `get_related_entities`, `_load_project` guards — these only widen options; verify no test asserts the old "block when no vendors" behavior.

**Medium-risk areas:**
- `_TX_ENTITY_TYPE_MAP`: relaxing purchase/sale validators could affect any code relying on the exact `is_vendor`/`is_client` predicates. Only the listed purchase/sale types change; other types are untouched.
- `_implicit_reversable_transaction_types`: only World-involved ops become implicitly reversible; non-World purchase/sale reversal behavior is unchanged (existing `test_reversal_blocked_when_payment_exists` must keep passing).
- `create_payment_transaction` full-settlement check: must be gated on `_counterparty_is_world` so normal partially-payable ops are unaffected.

**High-care areas:**
- Purchase/sale clean methods must keep rejecting non-World non-vendor/non-client destinations/sources exactly as today.
- The reversal guard in `transaction_reverse_view()` must only fire for World-involved payment transactions, not for normal purchase/sale payments (which remain individually reversible).

## Out of scope (flag for confirmation)

- Expense already uses World as destination (`project → world`) and remains partially payable / individually reversible — this plan does **not** change expense behavior. Confirm this is intended.
Don't touch expense.
- Adjustments on World-involved purchase/sale are allowed by the type map changes; if the fully-paid invariant must also hold after adjustments, add a follow-up guard.
Adjustment should be blocked also.


User: Too complicated , I wil decide later