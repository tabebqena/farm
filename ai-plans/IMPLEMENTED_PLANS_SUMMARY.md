# Implemented Plans — Consolidated Summary

> **Purpose:** consolidated record of the `ai-plans/*.md` plans that were **completely
> implemented**. The original per-plan files were removed on 2026-09-01 after this summary
> was created. Plans with pending, deferred, analysis-only, rejected, or partially-implemented
> actions were **kept as-is** in `ai-plans/` and are listed at the bottom.
>
> Grouping is by domain. Each entry notes what was implemented and its verification.

---

## 1. Inventory & Stock

### Animal Product Templates & Products — `animal_product_templates_plan.md` ✅ COMPLETE
- Extended [`ProductTemplate`](apps/app_inventory/models.py) with animal attributes: `Gender`
  choices, `animal_type`, `gender`, `produces` (asymmetrical self-M2M), `gives_birth_to`
  (self-FK), `can_die`, `can_be_consumed`.
- Extended [`Product`](apps/app_inventory/models.py) with `gender`, `birth_date`, `mother`
  (self-FK `related_name="offspring"`); added new [`MedicalRecord`](apps/app_animal/models.py) model.
- `clean()` validation (ANIMAL forces `can_be_consumed=False`; `gives_birth_to`/`produces`
  rules) and `accepts_operation()` gating (DEATH↔`can_die`, CONSUMPTION↔`can_be_consumed`).
- Full **birth flow**: mother/gender/birth-date fields on the create form, newborn template
  defaults to `gives_birth_to`, per-head attributes threaded through lazy product creation.
- `ProductTemplateForm` + Animal Attributes section; display templates; admin.
- Migration `0012_animal_product_template_fields.py`.
- **Verification:** `manage.py check` clean; `--parallel=8` → 1250 tests OK.

### Seed Animal Template Data — `seed-animal-template-data-plan.md` ✅ COMPLETE
- Replaced the ANIMAL seed with a **species × stage × gender** list-of-dicts (Cow / Buffalo /
  Sheep / Goat × Adult / Calf × FEMALE / MALE = 16 templates) with `tag_prefix`, `produces`
  (Meat + Manure), and `gives_birth_to` resolution (Adult Female → same-species Calf Female).
- Pruned all legacy animal templates (Fattening Cattle, Dairy Cows, Camels, Poultry, Rabbits…);
  FEED/MEDICINE/PRODUCT seed unchanged.
- Added `SeedCommandProductTemplatesTest` (6 tests: creation/attributes, four-species
  invariant, `gives_birth_to`, removed-template absence, non-animal flags, idempotency).
- **Verification:** `manage.py check` clean; `--parallel=8` → 1256 tests OK.

### Remove BATCH Tracking — `remove-batch-tracking-plan.md` ✅ executed
- Removed `BATCH` from `ProductTemplate.TrackingMode` (INDIVIDUAL / COMMODITY only);
  nature-based enforcement in `clean()`/`save()`; added `tag_prefix` and
  `ProductTemplate.next_tag(entity)`.
- One movement line per head → one tagged `Product`; forms auto-suggest/require tags for
  INDIVIDUAL templates; seed sets mode + prefix per nature.
- Migration `0011_producttemplate_tag_prefix_and_more.py` (schema only).
- **Verification:** `manage.py check` clean; `--parallel=8` → 1231 tests OK.

### Lazy Product Creation / Unified Movements — `lazy-product-creation-plan.md` ✅ done
- Unified all inventory operations under `InventoryMovementLine`; **products are created only
  when a movement records a physical transfer** (PURCHASE/BIRTH lazy creation), value-only
  capital ops stay direct.
- `record_movement_line()` `_MAP` for all 7 ops; `InventoryMovementLine.save()` lazy product
  creation; `save_inventory()` auto-movements for BIRTH/DEATH; `reverse()` restructured;
  removed stale `InventoryMovement` reference.
- `Product.status` derived from movement lines (+ `CONSUMED`); stock page Live/Dead/Consumed/
  Sold tabs.
- **Verification:** `manage.py check` clean.

### Inventory Phase A (+ Phase B ledger drop) — `inventory-phase-a-plan.md` ✅ implemented
- **Phase A:** `MedicalRecord` moved to the new `apps/app_animal` app (model, admin, tests,
  migration `0013` data copy); `Product.current_value` reconciled to movement/ledger-based
  valuation; `Product.status` **decoupled from operations** (movement/presence-based, fixing
  the partial-commodity-sale limitation).
- **Phase B:** **dropped `ProductLedgerEntry`**; new [`apps/app_inventory/stock.py`](apps/app_inventory/stock.py)
  is the single source of truth (`movement_state`, `portfolio`, `inventory_value`,
  `pending_items`/`pending_deliveries`, `capital_delta`); all call sites rewired; migration
  `0014` drops the table; `backfill_product_ledger` command and its test file removed.
- **Verification:** full suite `--parallel=8` → 1435 tests OK.

### Stock Detail & Stock History — `stock_detail_improvement.md` ✅ implemented
- Reworked [`stock_detail`](apps/app_inventory/views.py): per-product **physically-present
  cards** (ANIMAL = one card per head; commodity = quantity + unit), search, pagination, single
  Obligated-Outbound warning (Obligated Inbound removed), dynamic Moved/Not-Moved badge.
- New **Stock History** page over `InventoryMovementLine` with direction / op-type / search /
  date-range filters, pagination, reversal markers.
- **Verification:** full suite `--parallel=8` → 1429 tests OK.

### One-Step Consume from Stock — `consume-from-stock-plan.md` ✅ implemented
- Added `quick_consume()` in `apps/app_inventory` (POST-only): builds a single-item formset
  and delegates to the unchanged `ConsumptionOperation.create(...)`; guards for officer,
  ownership, nature (FEED/MEDICINE), availability (`state_as_of`), and `minimum_quantity`
  multiple.
- URL `entity/<pk>/stock/consume/` + inline "Consume" form on `stock_detail.html`; spec noted
  in `op_19_consumption.md`.
- **Verification:** inventory + inventory-op suites → 142 tests OK; `manage.py check` clean.

### Purchase Movement: One Product Line per Head — `fix-purchase-movement-product-per-line.md` ✅ implemented
- `_create_inventory_movement()` expands PURCHASE+INDIVIDUAL rows into **one qty-1 line per
  head with `product=None`** so `InventoryMovementLine.save()` lazy-creates a tagged `Product`
  per head (matching `create_from_session()` / deferred receipt). COMMODITY/SALE preserve the
  first-product derivation.
- Regression test `test_purchase_movement_creates_new_product_per_animal`.
- **Verification:** `manage.py check` clean; targeted → 304 tests OK.

### Operation Still "Received" After Movement Reversal — `fix-operation-received-after-reversal.md` ✅ implemented
- Added `active_lines_for_item()` to [`apps/app_inventory/stock.py`](apps/app_inventory/stock.py)
  (excludes reversal lines and reversed originals); `Operation.get_items_data()`,
  `InvoiceItem.build_movement_json()`, `InventoryMovementLine.clean()` over-delivery guard, and
  `register_deferred_movements()` now use it — reversed originals no longer count as moved.
- **Verification:** `--parallel=10 --keepdb` on inventory + purchase/sale + detail view → 303
  tests OK; `app_operation` + `app_adjustment` → 1118 tests OK.

### Stock Events Without Accounting Mixins — `stock-event-model-plan.md` ✅ DONE
- Split the base class: lean `Operation` (no accounting mixins) plus plain
  `TransactionMixin` / `AdjustableTransactionMixin` / `RepayableTransactionMixin` stacks.
- Birth / Death / Consumption / Capital Gain / Capital Loss now extend the **lean** `Operation`
  → they **no longer create `Transaction` rows** and carry no settlement/repayment/adjustment
  machinery; inventory behaviour and period/closed-period guards retained.
- Guarded shared views/templates (`effective_amount` base fallback, guarded settlement/
  payment/repayment reads); removed `CAPITAL_GAIN/LOSS/CONSUMPTION` from `Entity.profit_loss()`.
- Fixed `_reversable_transaction_types` AttributeError; updated specs + tests.
- **Verification:** `manage.py check` + `makemigrations --check` clean; full suite
  `--parallel=10 --keepdb` all pass.

---

## 2. Adjustments

### Adjustment Card Effect Indicator — `fix-adjustment-card-effect-indicator.md` ✅ implemented
- Added `Adjustment.is_reduction` instance property (template-friendly wrapper over
  `AdjustmentType.is_reduction`); `operation_detail.html` and `adjustments_list.html` now use
  it for the correct red/green + `-`/`+` display (previously `adj.amount < 0` never fired).

### InvoiceItemAdjustment Reversal Anomaly — `fix-item-adjustment-reversal-anomaly.md` ✅ implemented
- `Adjustment.reverse()` now **delegates to `InvoiceItemAdjustment.reverse()`** when a linked
  non-reversed item adjustment exists (`_from_item_adjustment` bypass flag prevents recursion),
  so direct reversal reverses financial + inventory sides and marks both records.
- Success message updated; direct-reversal delegation tests added.

### Hide Item-Correction Types from Admin Filter — `refactor-adjustment-types.md` ✅ implemented
- Added `FinancialAdjustmentTypeFilter` (SimpleListFilter) excluding the internal
  `*_ITEM_CORRECTION_*` types; `AdjustmentAdmin.list_filter` updated.

### Enhance `record_accounting_adjustment` Template — `enhance-record-adjustment-template.md` ✅ implemented
- `record_accounting_adjustment` view adds `adjustment_type_data` JSON + `prior_adjustments_net`
  to context; `record_adjustment.html` adds an amount summary, a **live JS after-adjustment
  calculator**, and a type-documentation panel.

---

## 3. Operations Engine & Proxies

### Birth Double-Count Fix (non-cash virtual ops) — `birth-double-count-fix-plan.md` ✅ IMPLEMENTED
- Made virtual value ops (Birth / Death / Capital Gain / Capital Loss) **non-cash**: removed
  `BIRTH/DEATH/CAPITAL_GAIN/CAPITAL_LOSS_PAYMENT` from `payment_types()` (kept constants/maps).
- `FinancialPeriod.end_assets` now uses **movement-based** `inventory_value(entity, end_date)`;
  deleted the now-unused `remaining_inventory_value` property.
- Ripple fix: seed helpers switched from `CapitalGainOperation` to `CorrectionCreditOperation`
  for spendable balance; type-specific assertions updated; specs updated.
- **Verification:** full suite `1448` tests pass; `manage.py check` clean.

### Dedicated Capital Valuation Link Table — `capital-valuation-dedicated-table-plan.md` ✅ implemented
- New [`ProductCapitalValuation`](apps/app_inventory/models.py) (signed `amount`) replaces the
  `InvoiceItem` M2M for Capital Gain/Loss; `stock.capital_delta()` sums non-reversed rows.
- Capital proxies flipped to `has_invoice=False`, `has_capital_valuation=True` +
  `add_valuation()`; fixed the latent `_create_operation` AttributeError in the evaluation view
  (now routes through `proxy_cls.create(...)`); `save_inventory()` no longer handles capital.
- Detail/list display snippets for capital valuations; migration `0015`.
- **Verification:** `check` + `makemigrations --check` clean; targeted 124 tests OK; full suite
  (excluding consumption) 1374 tests OK.

### Merge Capital Gain & Loss — `merge-capital-operations-plan.md` ✅ implemented
- Merged `CapitalGainOperation` + `CapitalLossOperation` into **`CapitalValuationOperation`**
  (per-type config dispatch on `operation_type`); `PROXY_MAP`/`_URL_MAP` map both types/slugs to
  the merged class; evaluation view resolves the variant from the delta sign.
- Migration `0011_merge_capital_proxies.py` (model-state only); specs consolidated into
  `capital_valuation_operation.md`.
- **Verification:** `check` + `makemigrations --check` clean; full suite 1472 tests OK (only
  pre-existing Selenium `ui_tests/` failures, unrelated).

### Merge Correction Credit & Debit — `merge-correction-operations-plan.md` ✅ implemented
- Merged `CorrectionCreditOperation` + `CorrectionDebitOperation` into **`CorrectionOperation`**;
  `_URL_MAP` registers every slug; `Operation.resolve_request` gained `operation_type` +
  `_type_config()`; create view resolves `canonical_op_type` from the URL slug; reverse view
  reads instance `operation.label`.
- Migration `0010_merge_correction_proxies.py` (model-state only).
- **Verification:** `check` + `makemigrations --check` clean; full suite 1472 tests OK (only
  pre-existing Selenium `ui_tests/` failures).

### Refactor One-Shot Operations & Mixins — `refactor-one-shot-operations-plan.md` ✅ completed
- Added `OneShotTransactionMixin` (config: one-shot flags, `max_payment_transaction_count=1`)
  and `AutoTransactionMixin` (shared `save()` plumbing, `_is_reversal_record()`) in
  `apps/app_base/mixins.py`; deduplicated the two `save()` reversal-skip branches; cleaned the
  flag comment block.
- Added public `Operation.is_one_shot`; one-shot proxies (cash, funding, refund, transfer,
  correction, worker advance) rebased and config removed; detail view uses `is_one_shot`.
- **Verification:** full app suite (ui_tests excluded) `--parallel=10 --keepdb` → 1428 tests OK.

### Refactor Inventory Operations & Mixins — `refactor-inventory-operations-mixins-plan.md` ✅ completed
- Added `InventoryOperationMixin` (inventory behaviour extracted verbatim from `Operation`:
  owner/receiving entities, `can_create_movement`, `get_items_data`, `save_inventory`,
  `_auto_create_inventory_movements`, plus reversal hooks) and `StockEventMixin` (shared
  non-accounting config); `Operation.reverse()` delegates to the two hooks.
- Stock-event proxies rebased to `StockEventMixin`; specs registration updated.
- **Verification:** `check` + `makemigrations --check --dry-run` clean; full app suite
  (ui_tests excluded) `--parallel=10 --keepdb` → 1435 tests OK.

### Move POST Business Logic to Model (`Operation.create`) — `refactor-post-to-model-create.md` ✅ implemented
- Added [`OperationDataValidator`](apps/app_operation/validators.py) (validates POST into
  `ParsedOperationData`) and `Operation.create()` classmethod orchestrating save → payment →
  invoice → inventory inside one atomic block; `OperationCreateView.post()` delegates.

### Refactor Birth/Death/Sale Views to `super().dispatch()` — `refactor-views-to-use-super-dispatch.md` ✅ implemented
- `OperationCreateView.dispatch()` now resolves `proxy_cls` from the URL `op_type` when present,
  else from the child class attribute; Birth / Death / Sale create views delegate to
  `super().dispatch()`; Sale client check moved from dispatch to `post()`; unused imports removed.

### Align `PurchaseOperation.create_from_session` with Base `Operation.create` — `refactor_purchase_create_from_session.md` ✅ implemented
- Added shared `Operation._validate_item_totals()` and `_build_invoice_items()`; both
  `PurchaseOperation` and `SaleOperation` `create_from_session()` use them and `process_payment()`
  (replacing the raw `create_payment_transaction()` call).

---

## 4. Accounting & Fixes

### Consumption as COGS on the Project P&L — `consumption-cogs-pnl-plan.md` ✅ Done (Option B)
- Added `CONSUMPTION_ISSUANCE` to the costs list in `Entity.profit_loss()` (COGS); removed
  `CONSUMPTION_PAYMENT` from `payment_types()` so consumption no longer drains the fund
  (payment tx still created for settlement bookkeeping).
- Reversal of a consumption negates the COGS (mirror `target=fund` signing); specs updated.
- **Verification:** inventory + period suites → 137 passed; full `--parallel=4` → 1215 passed.

### Inventory & Farm-Domain Integrity Fixes — `inventory-integrity-fixes-plan.md` ✅ all fixes implemented
- **Fix 1** ownership/location validation (`_outbound_owner_entity`, entity-filtered select
  forms, `save_inventory` guard, `Operation.inventory_owner_entity`; fixed a latent `NameError`).
- **Fix 2** availability guard (`_validate_availability` via `state_as_of`) + atomic auto-create.
- **Fix 3** concurrency (`Product.lock_ids()` `select_for_update`; payment fund row locked).
- **Fix 4** unit consistency (quantity multiple of `minimum_quantity`).
- **Fix 5** closed-period guard (`is_date_in_closed_period()` applied to payment/repayment/
  movement/adjustment views).
- **Fix 6** tag identity (INDIVIDUAL requires tag; `UniqueConstraint(entity, unique_id)`,
  migration `0010`).
- **Fix 7** internal-client Sale clone documented as intentional (no code change).
- **Fix 8** lifecycle: `Product.status` reversal-aware (reversed Death/Sale/Consumption restores
  ACTIVE) + reversal dependency guard.
- **Fix 9** valuation = purchase price (`valuation_unit_cost()`), with future-method comment.
- **Fix 10** docs sync (`operations-comparison.md`, per-op specs, `inventory_ledger.md`).

### Make the Test Suite Green — `make-tests-green-plan.md` ✅ Implemented
- Fixed genuine source bugs: `pk=None` guard in `InvoiceItemAdjustmentLine._before_effective_*`;
  `prefix="lines"` on the movement formset constructions in `create_inventory_movement()`; and
  `clean()` allowing a product whose status matches the operation's terminal status.
- Updated stale tests to the newer ledger design (issuance/movement types, `product_template`
  FK, obligated-only validation, issuance entries queried by `invoice_item`).
- **Verification:** `Ran 1183 tests ... OK` (was `FAILED (failures=4, errors=51)`).

### Fix the SALE Mechanism — `fix-sale-mechanism-plan.md` ✅ implemented
- Sale wizard now selects the seller's **existing products** (`sale_select_product_view` +
  `SaleItemForm` with `product_id`); `create_from_session()` affects the existing product via a
  `SALE_MOVEMENT` line (no fresh-product minting, no internal-client clone).
- Removed the second sale path (`SaleCreateView`, `sale_form.html`, `sale_create_view` route);
  the generic `OperationCreateView` redirects SALE to the wizard.
- **Verification:** full suite → 1434 tests OK.

### Fix Loan Repayment Without Disbursement — `fix-loan-repayment-without-disbursement-plan.md` ✅ completed
- Added `LinkedRePaymentTransactionMixin.repayable_amount = min(total_repayable_amount,
  amount_settled)`; `amount_remaining_to_repay` / `is_fully_repayed` / `is_overpaid_repayed`
  routed through it; detail view uses `repayable_amount`.
- Undisbursed loans are not repayable; tests updated/added (blocked-without-disbursement,
  capped-by-disbursement); spec `op_8_loan.md` updated.
- **Verification:** `manage.py check` OK; full project `--parallel=8` → 1415 tests OK.

### Fix "Fully Repaid" After Repayment Reversal — `fix-repayment-reversal-repaid-status-plan.md` ✅ completed
- `amount_repayed` now returns `to_source - from_source` (mirrors `amount_settled`), so mirror
  reversals of repayments net out and the repaid state is restored.
- Follow-up: payables/receivables exclude reversal mirrors —
  `Entity._tx_sum_excluding_reversed` and `_build_obligation_transactions` add
  `reversal_of__isnull=True`; audit trail preserved elsewhere.
- **Verification:** `--parallel=8` on touched modules → 44 tests OK; `app_operation` +
  `app_transaction` → 1006 tests OK; full suite → 1320 tests OK.

---

## 5. UI / Views / Reports

### Operation Detail Page — Navigation & Settlement UX — `operation-detail-page-improvement-plan.md` ✅ executed
- `add_related` nav override adds an operations-list link per non-virtual counterpart entity;
  `address_bar.html` shows repayment progress for `has_repayment` ops; Record Payment / Record
  Repayment buttons hidden when fully settled / fully repaid.

### Operations List View — Appearance & UX — `operations-list-view-improvement-plan.md` ✅ executed
- Added a **Current Balance** card; removed "Customize Columns"; responsive rows with
  kind-aware status badges (`one_shot` / `paid` / `repayed`) and a settlement progress bar;
  enriched display list (paid / remaining / total / percent) with pagination.

### Operations Comparison — Operation Column — `operations-comparison-operation-column.md` ✅ implemented
- Added a full **Operation** name column to all 19 tables in
  `docs/specs/operations/operations-comparison.md` and expanded prose code lists to
  `CODE (Full Name)`.

### Source Fund Display on Create Pages — `source-fund-display-on-create-pages-plan.md` ✅ implemented
- Reusable `fund-balance.html` snippet shown on operation create pages, evaluation form,
  purchase/sale wizards + invoices, and payment/repayment forms; `source_entity` /
  `source_balance` / `currency` context added; fixed `HasTagSelect.create_option` `subindex`
  TypeError.

### Entity Detail Financial Summary + Payables/Receivables Pages — `entity-detail-financial-summary-plan.md` ✅ implemented
- "Financial Summary" card on entity detail (balance / payables / receivables / stock value);
  new payables + receivables pages sharing `_build_obligation_transactions` / `_obligation_context`;
  transactions list renamed to **Payment Transactions**.

### Entity Transactions List (Balance Tracking) — `entity-transactions-list-plan.md` ✅ implemented
- `entity_transactions_view` lists payment-type transactions with direction + running balance +
  summary cards, paginated; transaction **detail** page replaces the one-click reverse
  (`can_reverse` guard); nav + entity detail links added.

### User Profile & Login Redirect — `user-profile-and-login-redirect-plan.md` ✅ implemented
- Profile link in the user dropdown; read-only profile detail + `profile_edit` view/URL/template;
  `LOGIN_REDIRECT_URL` → `/` with `next` preserved on the login form.

### Financial Reports in the UI — `financial-reports-ui-plan.md` ✅ implemented
- New `apps/app_report` app: hub + Income Statement, Balance Sheet, Cash Flow, Statement of
  Changes in Equity (period-scoped, accounting-style layouts, drill-down links, print-friendly);
  `reporting.py` helpers; optional `?type=` filter on the payment-transactions page; nav links.
- **Verification:** `check` clean; `app_report` 22/22; affected suites 176/176.

---

## 6. Tests & Cleanup

### Improve the Operation Test Suite — `improve-operation-test-suite-plan.md` ✅ Phases A–E done
- **Phase A:** shared infra in [`apps/app_operation/tests/base.py`](apps/app_operation/tests/base.py)
  (fixtures + exact-value helpers `assert_tx`, `assert_tx_types`, `assert_balance`,
  `assert_payables`, `assert_receivables`, `snapshot_state`, `assert_state_unchanged`…).
- **Phase B:** WORKER_ADVANCE pilot split into one-side-effect-per-test.
- **Phase C:** filled the matrix gaps — reverse→SE4 for every obligation-bearing type,
  differential invariants, SE5 exact negation sets, SE7 product-status restoration.
- **Phase D:** strengthened `.exists()`/`.count()` → exact-value assertions across the suite.
- **Phase E:** filled-in audit matrix. (The `COVERAGE_MANIFEST` + `CoverageManifestTest`
  executable drift guard added in this phase was removed later — see CHANGES.md.)
- **Verification:** `app_operation + app_transaction + app_inventory + app_adjustment +
  app_entity` → 1377 tests OK.

### Operations Spec — Test-Coverage Closure — `operations-spec-test-coverage-closure-plan.md` ✅ implemented
- Closed VR4 reversal-dependency-guard gaps (consumption partial-then-full, sale
  partial-then-full); added SR9/SR10 tests (settlement cleared, reason flows to reversal) to the
  one-shot reversal suites.
- Coverage-doc pass: filled every "Pinned by test" / "Verified by" / §10 cell with real test
  names; automated checker confirmed all **699** `ClassName.method` refs resolve.
- **Verification:** full suite `--parallel=10 --keepdb` → 1432 tests OK (only pre-existing
  Selenium UI failures).

### Remove Profit Distribution & Loss Coverage — `remove-profit-distribution-loss-coverage-plan.md` ✅ executed
- Removed the two operations (proxies, `OperationType` values, `ShareholderAllocation`,
  `Operation.plan`), their 4 transaction types + registrations, UI items, tests, migrations
  (schema-only, historical rows kept), and specs/docs/locale references.
- **Verification:** `check` + `makemigrations --check --dry-run` clean; full suite (fresh DB)
  → 1325 tests OK.

---

## Files kept as-is (not summarized / not deleted)

The following files remain untouched because they are analysis-only, deferred, rejected,
pending, partially implemented, or standing documents:

- `adjustment-with-movements-plan.md` — only the `_sync_products` removal was done; warning
  flash + detail warning card not implemented.
- `auto-ui-test-suite-plan.md` — harness + 44 UI tests implemented but documented gaps remain
  (op_5/6, op_12–14, op_17–19, feature specs, global flows).
- `consumption-vs-expense-analysis.md` — analysis document with deferred decisions.
- `expense-stockable-block-plan.md` — rejected / superseded (no code change).
- `internal-entity-transfer-stock-plan.md` — implemented but with "Not done (documented)" items
  (reversal convenience, disposal-aware status).
- `inventory-app-simplification-analysis.md` — analysis only.
- `inventory-ledger-drop-summary.md` — resume document listing deferred next steps.
- `inventory-lifecycle-audit-plan.md` — analysis; changes deferred pending design decisions.
- `ledger-entry-type-redesign.md` — superseded by the ledger drop.
- `manual-test-plan.md` — standing manual-test document (not an implementation plan).
- `move_view_logic_to_models.md` — only some phases were completed via other plans.
- `production-output-path-plan.md` — planning, not implemented.
- `purchase-save-inventory-analysis.md` — analysis only.
- `stock-products-movements-mechanism-review.md` — analysis only, implementation deferred.
- `world-entity-vendor-client-plan.md` — pending user decision.
- `manual-test-results.csv` — data file (kept).
