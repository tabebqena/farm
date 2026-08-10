# Plan — Production/Output Path for `PRODUCT` Nature (Milk, Meat)

**Status:** Planning — not implemented.
**Date:** 2026-08-10
**Parent:** [`ai-plans/consumption-vs-expense-analysis.md`](consumption-vs-expense-analysis.md) (deferred item).
**Scope:** `apps/app_operation` (operation type, proxy, views), `apps/app_transaction/transaction_type.py`, `apps/app_inventory/models.py`, seed + migrations + specs.

---

## 1. Goal

Let **production output** (milk, meat) enter inventory as an asset and then be sold. Today milk/meat are seeded as `nature=PRODUCT` ([`seed.py:95`](../apps/app_base/management/commands/seed.py:95)) but `PRODUCT` allows only `PURCHASE`/`SALE`/`CAPITAL_*` ([`ProductTemplate._ALLOWED_OP_TYPES`](../apps/app_inventory/models.py:561)) — there is **no operation that creates production output**, so milk can only "enter" by being (incorrectly) purchased.

---

## 2. Context

- **Birth** already creates ANIMAL assets: `system → project`, one-shot, auto movement lines, `BIRTH_MOVEMENT` ledger ([op_17](../specs/operations/op_17_birth.md)).
- A production op should mirror Birth but target **PRODUCT** nature (agricultural produce at point of harvest, IAS 41 fair-value-less-costs-to-sell — or a recorded production cost, pending decision).
- Seed data: `Raw Milk`, `Meat (Live Weight)` are `PRODUCT` templates ([`seed.py:95`](../apps/app_base/management/commands/seed.py:95)).

---

## 3. Design decision (choose one)

### Option A — `PRODUCTION` operation mirroring Birth (recommended MVP)
New operation type `PRODUCTION`:
- `source = system` (virtual value creation), `destination = project`, one-shot auto-settled, `creates_assets=True`, `has_invoice=True`.
- Auto-creates movement lines and ledger entries; product status → ACTIVE.
- User records quantity + unit price per output item (production cost or market value — see decision below).

- ✅ Reuses the entire Birth machinery (`_auto_create_inventory_movements`, lazy product creation, ledger).
- ❌ Does not yet tie output to the producing animal or to feed consumed.

### Option B — Production with inputs (producer + feed consumption)
`PRODUCTION` optionally references a producing ANIMAL and consumes FEED/MEDICINE inputs as part of production (debit feed, credit milk).
- ✅ Full cost-of-production tracking (milk produced from X kg feed).
- ❌ Significantly more complex (multi-part form, conversion logic, ledger for both directions) — a follow-up feature, not the MVP.

### Option C — Reuse `BIRTH` for PRODUCT
Extend Birth/`_ALLOWED_OP_TYPES` so `PRODUCT` can use BIRTH.
- ✅ Least code.
- ❌ Semantically wrong (milk is not "born"); conflates livestock birth with produce harvest; bad reporting.

**Recommendation:** Option A as MVP; document Option B as a future enhancement.

---

## 4. Implementation steps (Option A)

1. **Operation type** — add `PRODUCTION = "PRODUCTION", "Production"` to [`OperationType`](../apps/app_operation/models/operation_type.py:4).
2. **Transaction types** — add `PRODUCTION_ISSUANCE` + `PRODUCTION_PAYMENT` to [`TransactionType`](../apps/app_transaction/transaction_type.py) with entity mapping `(system, project)` and operation mapping `Production` (mirror BIRTH at lines ~544 / ~628).
3. **Proxy** — add `apps/app_operation/models/proxies/op_production.py` `ProductionOperation` (mirror [`op_birth.py`](../apps/app_operation/models/proxies/op_birth.py)): `_source_role="system"`, `_dest_role="url"`, one-shot, `creates_assets=True`, `has_invoice=True`; export in `proxies/__init__.py` + `PROXY_MAP`.
4. **Nature matrix** — add `PRODUCTION` to `ProductTemplate._ALLOWED_OP_TYPES["PRODUCT"]` ([`models.py:561`](../apps/app_inventory/models.py:561)).
5. **Ledger** — add `PRODUCTION_ISSUANCE` + `PRODUCTION_MOVEMENT` entry types to [`ProductLedgerEntry.EntryType`](../apps/app_inventory/models.py:52), the `_MAP` in [`record()`](../apps/app_inventory/models.py:175), `MOVEMENT_TYPES`, and the `_MOVEMENT_TYPE_MAP` in [`record_movement_line()`](../apps/app_inventory/models.py:319) (+1/+1 inbound).
6. **Product status** — add `PRODUCTION → ACTIVE` to [`Product.status`](../apps/app_inventory/models.py:862) `STATUS_CHANGING_TYPES`/`TYPE_TO_STATUS`.
7. **Inventory owner** — confirm [`Operation.inventory_owner_entity`](../apps/app_operation/models/operation.py:123) needs no change for inbound (returns None for inbound already).
8. **Views/forms** — add a create view + item formset (mirror the Birth create view) and a URL entry; template reuse `generic_form.html` or a dedicated production form.
9. **Valuation decision** — record output at (a) entered unit price (production cost) or (b) market/fair value (IAS 41). Default to entered unit price for consistency with the rest of the ledger (purchase-value decision).
10. **Migration** — one migration adding the new choices (entry types + operation/transaction types are CharField choices — extend, no schema change unless a field is added).
11. **Tests + spec** — mirror Birth tests (`test_birth_*`), add `test_production_production_create.py` / `_reversal.py`; write [`specs/operations/op_20_production.md`](../specs/operations/op_20_production.md); update `operations-comparison.md`.

---

## 5. Verification

- `python manage.py test apps.app_operation.tests.operations.inventory apps.app_inventory.tests --parallel=4`
- `python manage.py check`

---

## 6. Implementation status

*(To be filled in after execution.)*
