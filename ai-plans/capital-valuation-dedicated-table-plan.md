# Plan — Dedicated Capital Valuation Link Table for Capital Gain/Loss

## Goal

Replace the current mechanism that carries Capital Gain / Capital Loss **value** on an
[`InvoiceItem`](apps/app_inventory/models.py:272) linked to a product via the `Product.invoice_items` M2M,
with a **dedicated table** that links a `Product` to its signed capital gain/loss value.

All existing guards and features must be preserved — most importantly:
- value flows through inventory (`capital_delta` → `movement_state` → `inventory_value` / `current_value` / `end_assets`)
- **reversability** (operation-level: a reversed gain/loss stops contributing to value)
- value-only (no `InventoryMovementLine`, no quantity change, product stays ACTIVE)
- no accounting transactions, no settlement, no `profit_loss()` impact, period assignment

## Decisions (confirmed with user)

1. **Replace entirely.** Capital Gain/Loss stop creating `InvoiceItem` rows. Flip `has_invoice = False`
   on both proxies and add `has_capital_valuation = True`. The new table is the single source of value,
   display, and reversal.
2. **Operation-level reversal + signed amount.** Rows carry a signed `amount` (gain `+`, loss `−`), no
   `reversal_of` on the row. `capital_delta()` excludes rows whose operation has been reversed
   (`operation__reversed_by__isnull=True`), exactly mirroring today's semantics.
3. **Greenfield, no data backfill.** Existing capital `InvoiceItem` rows in dev DB stay as historical
   records and are simply no longer consulted. Tests and fresh data use only the new table.
4. **Keep the operations as the container.** `CapitalGainOperation` / `CapitalLossOperation` are NOT
   removed. The dedicated table replaces only the **value-carrying link** (the `InvoiceItem` M2M). The
   operation continues to provide period assignment, closed-period guards, op-level reversal, officer/audit,
   and the operation history/detail UI — exactly like `InvoiceItem`/`InventoryMovementLine` are details of
   their parent operation. This preserves all guards/behaviour with minimal blast radius.

---

## Current mechanism (being replaced)

- Create (view): [`EvaluationCreateView.post()`](apps/app_operation/views/create_operation/evaluation.py:115)
  computes the delta via [`Product.compute_valuation_delta()`](apps/app_inventory/models.py:937), picks the proxy,
  then manually creates an `InvoiceItem` and links the product:
  [`evaluation.py:204-214`](apps/app_operation/views/create_operation/evaluation.py:204).
- Create (model/test): `make_invoice_item(op, template, qty, price)` + `product.invoice_items.add(item)`
  ([`tests/general.py:80`](apps/app_inventory/tests/general.py:80)).
- Value read: [`stock.capital_delta()`](apps/app_inventory/stock.py:90) scans `product.invoice_items` for
  non-reversed `CAPITAL_GAIN`/`CAPITAL_LOSS` ops, sums `sign × (quantity × unit_price)`.
- Reversal: op-level only — `capital_delta` filters `operation__reversed_by__isnull=True`.
- Display: `has_invoice=True` drives the detail view items section
  ([`detail.py:51`](apps/app_operation/views/detail.py:51)) and
  [`invoice_items_list_view`](apps/app_operation/views/invoice_items.py:50).

**Latent bug found:** [`evaluation.py:204`](apps/app_operation/views/create_operation/evaluation.py:204) calls
`self._create_operation(...)`, which is **not defined anywhere**. The evaluation POST path fails at runtime
today. This plan fixes it by routing creation through `self.proxy_cls.create(...)`.

---

## New model

Add to [`apps/app_inventory/models.py`](apps/app_inventory/models.py) (place near `InventoryMovementLine`):

```python
class ProductCapitalValuation(ImmutableMixin, BaseModel):
    """Value-only capital gain/loss entry: links a Product to a signed value for a
    Capital Gain/Loss operation. No physical movement is recorded."""

    _immutable_fields = {
        "operation": {},
        "product": {},
        "amount": {},
        "date": {},
    }

    operation = models.ForeignKey(
        "app_operation.Operation",
        on_delete=models.PROTECT,
        related_name="capital_valuations",
        verbose_name=_("operation"),
    )
    product = models.ForeignKey(
        "Product",
        on_delete=models.PROTECT,
        related_name="capital_valuations",
        verbose_name=_("product"),
    )
    amount = models.DecimalField(
        _("amount"), max_digits=15, decimal_places=2
    )  # signed: +gain / −loss
    date = models.DateField(_("date"), default=today_date.today)
    notes = models.TextField(_("notes"), blank=True)
    officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="capital_valuations_supervised",
        verbose_name=_("officer"),
        null=True,
        blank=True,
    )
```

**Validation (`clean()` / creation helper):**
- `operation.operation_type` is `CAPITAL_GAIN` or `CAPITAL_LOSS`.
- `amount` is nonzero and its sign matches the operation type (`+` gain, `−` loss).
- `product` is ACTIVE (reuse `Product.validate_active(allow_reversal=...)` for reversals).
- Ownership guard (VC10): `product.entity_id == operation.inventory_owner_entity_id`.
- Template compatibility: `product.product_template.accepts_operation(operation.operation_type)`.
- No `InventoryMovementLine` is ever created (structural).

**Creation entry point** — method on the capital proxies:

```python
def add_valuation(self, product, amount, officer=None, notes=""):
    from apps.app_inventory.models import ProductCapitalValuation
    entry = ProductCapitalValuation(
        operation=self, product=product, amount=amount,
        date=self.date, notes=notes, officer=officer,
    )
    entry.full_clean()
    entry.save()
    return entry
```

---

## Implementation steps

### 1. Model + migration
- Add `ProductCapitalValuation` to [`apps/app_inventory/models.py`](apps/app_inventory/models.py).
- `python manage.py makemigrations app_inventory` (schema migration; no data migration per decision 3).
- Register in [`apps/app_inventory/admin.py`](apps/app_inventory/admin.py) (optional, minor).

### 2. Proxies
- [`op_capital_gain.py`](apps/app_operation/models/proxies/op_capital_gain.py) and
  [`op_capital_loss.py`](apps/app_operation/models/proxies/op_capital_loss.py):
  - `has_invoice = False`
  - `has_capital_valuation = True`
  - add `add_valuation(product, amount, officer=None, notes="")`.
- Add a `has_capital_valuation` class attribute default (`False`) on the `Operation` base
  ([`operation.py:100`](apps/app_operation/models/operation.py:100)) and include it in
  `_operation_config` ([`operation.py:245`](apps/app_operation/models/operation.py:245)) for parity with
  `has_invoice`.

### 3. Value read — rewrite `capital_delta()`
[`apps/app_inventory/stock.py:90`](apps/app_inventory/stock.py:90):
```python
def capital_delta(product) -> Decimal:
    entries = product.capital_valuations.filter(
        operation__reversed_by__isnull=True
    ).select_related("operation")
    return sum((e.amount for e in entries), Decimal("0"))
```
This keeps `movement_state()`, `inventory_value()`, `current_value`, and `end_assets` unchanged in behavior.

### 4. Create path
- [`evaluation.py`](apps/app_operation/views/create_operation/evaluation.py:178-221):
  - Fix the latent bug: replace `self._create_operation(amount, date, description)` with the standard
    `self.proxy_cls.create(operation_type=..., source=..., destination=..., amount=amount, date=date,
    description=description, officer=request.user, amount_paid=Decimal("0"), project=self.project)` call
    (mirrors [`base.py:238`](apps/app_operation/views/create_operation/base.py:238)).
  - Replace the `InvoiceItem.objects.create(...)` + `product.invoice_items.add(item)` block with
    `op.add_valuation(product=product, amount=<signed delta>, officer=request.user)`.
  - Keep VC9 (material delta ≥ 0.01), VC10 (ownership), `product.validate_active()`.
- [`Operation.save_inventory()`](apps/app_operation/models/operation.py:831-869): the `CAPITAL_GAIN` /
  `CAPITAL_LOSS` branch currently does `selected.invoice_items.add(item)`. Since capital ops no longer create
  invoice items, change this branch to create `ProductCapitalValuation` rows (keep DEATH/CONSUMPTION behavior
  untouched). This preserves the spec's "SC5 implemented by save_inventory" mapping for any path that reaches it.

### 5. Display (detail + list)
- [`operation_detail_view`](apps/app_operation/views/detail.py:51): when `type(operation).has_capital_valuation`,
  fetch `operation.capital_valuations.select_related("product", "product__product_template", "officer")`
  and pass into context as `capital_valuations`; leave `items=None` (capital ops now have `has_invoice=False`).
- New snippet `templates/app_operation/snippets/detail/capital_valuations.html` rendering product, signed
  amount (gain/loss badge), date, officer; include it in
  [`operation_detail.html:13`](apps/app_operation/templates/app_operation/operation_detail.html:13) guarded by
  `has_capital_valuation`. The existing `invoice_items.html` and `inventory_movement_status.html` snippets are
  already `{% if items %}`-guarded, so they disappear automatically.
- [`invoice_items_list_view`](apps/app_operation/views/invoice_items.py:50): branch on
  `has_capital_valuation` — fetch `capital_valuations` and render a capital-valuation list instead of the
  "no invoice items" alert. Either extend `invoice_items_list.html` or add
  `capital_valuations_list.html`; update `invoice_items_list_view` context accordingly.

### 6. Consumers audit (verify no regressions)
- `Product.clean()` ([`models.py:828`](apps/app_inventory/models.py:828)) iterates `invoice_items` for
  compatibility — capital compatibility moves into `ProductCapitalValuation.clean()`; `Product.clean()`
  unchanged.
- `_status_from_linked_operations()` ([`models.py:675`](apps/app_inventory/models.py:675)) — capital types
  are not in `STATUS_CHANGING_TYPES`, so removing the M2M link does not change status; a capital-only product
  stays ACTIVE (SC6). No code change.
- `is_physically_moved` / `is_obligated_only` — movement-line based only; unaffected.
- `Operation.reverse()` guard branches ([`operation.py:1035`](apps/app_operation/models/operation.py:1035),
  `:1073`) — capital ops not in the movement sets; reversal still clones the op, valuation rows stay keyed to
  the original, and `capital_delta()` drops them once `reversed_by` is set. SR1–SR8 preserved.

### 7. Tests

**Update** (replace `make_invoice_item` + `invoice_items.add` with `op.add_valuation(...)` /
`ProductCapitalValuation.objects.create(...)`):
- [`test_capital_gain_capital_gain_reversal.py`](apps/app_operation/tests/operations/capital/test_capital_gain_capital_gain_reversal.py) (`_link` helper ~line 175)
- [`test_capital_loss_capital_loss_create.py`](apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_create.py) (`test_capital_loss_is_value_only_no_movement_line` ~line 252 — also assert no `InvoiceItem`)
- [`test_capital_loss_capital_loss_reversal.py`](apps/app_operation/tests/operations/capital/test_capital_loss_capital_loss_reversal.py) (~line 176)
- [`test_product.py`](apps/app_inventory/tests/test_product.py) (`_make_valued_product` ~line 133, `test_current_value_adds_capital_gain` ~line 185, `test_status_active_after_capital_gain` ~line 205)
- [`test_period_model.py`](apps/app_operation/tests/period/test_period_model.py) (`test_capital_gain_reflected_once_in_inventory_not_cash` ~line 438, capital loss counterpart ~line 475)
- [`test_evaluation_ownership.py`](apps/app_operation/tests/views/test_evaluation_ownership.py) if it asserts invoice items

**Add:**
- New model tests (`ProductCapitalValuation`): sign-vs-op-type, ownership guard, template compatibility,
  immutability.
- SC5 parity: capital op creates a valuation row + **no** `InventoryMovementLine` + **no** `InvoiceItem`.
- SC4: `movement_state` / `current_value` / `inventory_value` rise by the signed amount.
- SR5: after `op.reverse()`, value returns to baseline.
- Detail view: capital valuation section renders.
- Optionally extend the coverage manifest in [`tests/base.py`](apps/app_operation/tests/base.py) for the
  value-only branch.

### 8. Spec updates (spec-first per repo convention)
- [`op_5_capital_gain.md`](docs/specs/operations/op_5_capital_gain.md) and
  [`op_6_capital_loss.md`](docs/specs/operations/op_6_capital_loss.md):
  - §1 identity: `has_invoice` → `False`, add `has_capital_valuation=True`; update the `has_invoice` flag row.
  - §2.5 inventory layer: "Value-only: links the product to the invoice item; no movement line" →
    "creates a `ProductCapitalValuation` row; no movement line".
  - §5.1.2 SC5 wording: "the gain creates a `ProductCapitalValuation` row linked to the product but **no**
    `InventoryMovementLine`".
  - §8 view contract and §10 coverage matrix: reference the capital-valuation list/detail sections.
- [`operations-comparison.md`](docs/specs/operations/operations-comparison.md) row CG if it mentions invoice
  items.

### 9. Verification
- `python manage.py check`
- `python manage.py makemigrations --check`
- Targeted: `python manage.py test app_operation.tests.operations.capital app_inventory.tests.test_product app_operation.tests.period.test_period_model app_operation.tests.views.test_evaluation_ownership`
- Then full suite per repo rules (parallel, capture to `tmp/`, then delete the temp file).

---

## Out of scope
- No data backfill / cleanup of existing capital `InvoiceItem` rows (decision 3).
- No line-level (`reversal_of`) reversal on the new table (decision 2).
- No changes to the shared generic create formset machinery beyond the `has_invoice=False` flip (capital ops
  are created only via the evaluation view).

---

## Implementation notes (2026-08-14)

Implemented as planned, with these concrete changes:

**Model**
- Added `ProductCapitalValuation` ([`apps/app_inventory/models.py`](apps/app_inventory/models.py)) — `ImmutableMixin`,
  signed `amount`, FKs to `operation`/`product`, `date`, `officer`, `notes`. `clean()` enforces: op type is
  CAPITAL_GAIN/CAPITAL_LOSS, signed amount matches the direction (nonzero), ownership guard
  (`product.entity == operation.inventory_owner_entity`), template compatibility, and
  `product.validate_active(allow_reversal=…, allow_obligated=True)` — terminal-status products are still
  rejected (SC6); obligated-only products are allowed since a value write-up needs no physical presence.
- Migration `0015_productcapitalvaluation` + admin registration.

**Proxies / config**
- `CapitalGainOperation` / `CapitalLossOperation`: `has_invoice=False`, `has_capital_valuation=True`, and
  `add_valuation(product, amount, officer=None, notes="")` (creates + `full_clean()`s the row).
- `Operation` base: `has_capital_valuation = False` default + included in `_operation_config`.

**Value read**
- [`stock.capital_delta()`](apps/app_inventory/stock.py) now sums `product.capital_valuations` amounts where
  `operation__reversed_by__isnull=True` (signed). `movement_state`, `inventory_value`, `current_value`,
  `end_assets` behaviour unchanged.

**Create path**
- Fixed the latent `_create_operation` AttributeError in
  [`evaluation.py`](apps/app_operation/views/create_operation/evaluation.py) by calling `self.proxy_cls.create(...)`
  then `op.add_valuation(...)`; removed the `InvoiceItem` creation + M2M link.
- `Operation.save_inventory()` no longer handles CAPITAL_GAIN/LOSS (no invoice items exist for them); the loop
  now covers DEATH/CONSUMPTION only.

**Display**
- Detail view passes `capital_valuations` + `has_capital_valuation`; new snippet
  `snippets/detail/capital_valuations.html` (product, signed amount, date, officer) included in
  `operation_detail.html`.
- `invoice_items_list_view` renders the capital-valuation list for `has_capital_valuation` operations
  (instead of the "no invoice items" alert).

**Tests**
- Updated capital gain/loss create/reversal, `test_product.py`, and `test_period_model.py` to use
  `add_valuation` instead of invoice items.
- New `apps/app_inventory/tests/test_capital_valuation.py`: model guards (sign, zero, wrong op type, ownership,
  immutability), SC5 parity (valuation row + no InvoiceItem + no movement line), SC4 value rise/fall, SR5
  value restored on reversal, and a detail-view rendering test.

**Specs**
- `op_5_capital_gain.md`, `op_6_capital_loss.md` (flags, §2.5, SC5, §8, §10) and
  `operations-comparison.md` (CG/CL rows) updated to the dedicated-table model.

**Verification**
- `manage.py check` clean; `makemigrations --check` clean.
- Targeted suite (capital + product + period + evaluation-ownership + new valuation tests): 124 tests OK.
- Full suite excluding consumption tests (another instance owns them): 1374 tests OK.
- Temporary test-output files in `tmp/` removed after review.
