# Consumption
**Epic:** Inventory / Livestock — One-Shot
**Type:** One-shot, auto-settled, removes assets (`has_invoice=True`)

**Transaction flow:**
- Issuance: `project → system.fund` — type: `CONSUMPTION_ISSUANCE`
- Payment: `project → system.fund` — type: `CONSUMPTION_PAYMENT`

**Actions:** create, reverse.

## P&L / Accounting (COGS, Option B)
Consumed feed/medicine is recognized as **Cost of Goods Sold (COGS)** that reduces
the project's own profit in the period it is consumed — matching the feed cost to the
period of the milk/meat revenue it helps produce.

- `CONSUMPTION_ISSUANCE` is counted in [`Entity.profit_loss()`](../../apps/app_entity/models/__init__.py) costs, so the P&L and
  `FinancialPeriod.amount` reflect consumed feed/medicine in the consumption period.
- `CONSUMPTION_PAYMENT` is **not** a payment type anymore (removed from
  [`TransactionType.payment_types()`](../../apps/app_transaction/transaction_type.py)), so consumption does **not** drain the fund
  balance (`balance_at()` is unchanged). The consumed value moves from the inventory
  asset (ledger) to COGS on the P&L — a clean internal transfer on the project's books.
- `end_assets` (cash balance + remaining inventory) and the P&L both reflect
  consumption **exactly once**.
- Reversal of a consumption negates the COGS: the reversal issuance restores profit
  and keeps the fund balance unchanged.

## create
**Validation:**
- Source must be a Project entity
- Destination must be the System entity (`is_system=True`)
- Both entities `active=True`; source fund `active=True`
- Amount must be positive
- Officer must be a Person with `auth_user`, `auth_user.is_staff=True`, and `active=True`
- Balance @ create: **exempt** (no-balance write-off) — `E@create` pay (one-shot)

**Success effects:**
- `CONSUMPTION_ISSUANCE` + `CONSUMPTION_PAYMENT` created on save
- Immediately settled (`is_fully_settled=True`)
- Fund deltas: **no cash movement** — the payment is non-cash (not a payment type);
  COGS reduces the project P&L instead
- ✓ product ledger issuance **and** auto-created movement lines (`_auto_create_inventory_movements()` now includes CONSUMPTION, mirroring DEATH)
- ✓ `CONSUMPTION_MOVEMENT` ledger entry written per movement line (valued at the product's carried cost)
- ✓ Product status → `CONSUMED` (blocked from new operations unless reversed/adjusted)

**Inventory validation (enforced):**
- Availability: quantity must not exceed the product's physically-present on-hand (ledger)
- Ownership: the selected product must belong to the source project
- Unit consistency: quantity must be a multiple of `product_template.minimum_quantity`

## quick-consume from stock (one-step shortcut)
A lightweight entry point on the stock detail page (`quick_consume`) removes the
friction of the full consumption form for daily feeding: pick the product and a
quantity, click **Consume**, and the whole pipeline runs in one POST.

- View: [`quick_consume()`](../../apps/app_inventory/views.py) — POSTs a minimal
  form (`product_id`, `quantity`, `unit_price`, optional `date`/`description`),
  builds the single-item formset internally, and delegates to the unchanged
  `ConsumptionOperation.create(...)` factory — so issuance + payment
  transactions, the auto movement line, the `CONSUMPTION_MOVEMENT` ledger entry,
  and the `CONSUMED` product status all reuse the proven path.
- Route: `entity/<int:entity_pk>/stock/consume/` (name `quick_consume`) in
  [`apps/app_inventory/urls.py`](../../apps/app_inventory/urls.py).
- Guards (checked in the view for a friendly message and again at the model
  layer via `InventoryMovementLine.clean()`): ownership, nature (FEED/MEDICINE
  only), availability (`quantity ≤ state_as_of(...)["quantity"]`), unit
  multiple of `minimum_quantity`, and officer (`is_staff`).
- Redirects back to the stock detail page on success or error (Django message).

**Tests:** [`test_quick_consume_from_stock.py`](../../apps/app_inventory/tests/test_quick_consume_from_stock.py).

## reverse
**Validation:**
- Not already reversed / not a reversal / reason required
- Reversal dependency guard: blocked if the product was moved again in a later non-reversed outbound operation

**Success effects:**
- Reversal record; counter-transactions for issuance + payment
- Negated product ledger entries
- ✓ Auto-created movement lines reversed (reversal lines linked via `reversal_of`)
- ✓ Product status **restored to ACTIVE** (`Product.status` is reversal-aware — reversed operations are excluded)
- ✓ P&L restored: the reversal negates the `CONSUMPTION_ISSUANCE` COGS; fund balance stays unchanged

**Tests:** [`test_consumption_consumption_create.py`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py), [`test_consumption_consumption_reversal.py`](../../apps/app_operation/tests/operations/inventory/test_consumption_consumption_reversal.py), [`test_consumption_stock_detail.py`](../../apps/app_operation/tests/operations/inventory/test_consumption_stock_detail.py).
