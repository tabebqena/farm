# Refactor: Rewrite All Views as Class-Based Views

## Context

The user requested: **rewrite all views in a class based view**.

Per discussion, the agreed scope and style are:

- **Scope**: Convert every function-based view (FBV) to a class-based view (CBV), **except**:
  - The session-based **sale/purchase wizards** (`sale_wizard_*`, `purchase_wizard_*` in `apps/app_operation/views/create_operation/`)
  - The **6-step project setup wizard** (`project_setup_wizard_view` in `apps/app_entity/views/project_setup_wizard.py`)
  - The 4 **error handlers** in [`farm/views.py`](../farm/views.py) (`handler404/500/403/400`) — Django invokes these directly as callables `(request, exception)`; they must remain functions.
  - Views that are **already CBV** (no change): [`LoginView`](../apps/app_base/views.py:9), [`OperationCreateView`](../apps/app_operation/views/create_operation/base.py:74), [`BirthCreateView`](../apps/app_operation/views/create_operation/create_birth_view.py:7), [`DeathCreateView`](../apps/app_operation/views/create_operation/create_death_view.py:7), [`EvaluationCreateView`](../apps/app_operation/views/create_operation/evaluation.py:20).
- **Style**: Follow the repo's existing CBV convention — plain `django.views.View` with explicit `get(self, request, *args, **kwargs)`, `post(...)`, and `dispatch(...)` methods (the pattern established by `OperationCreateView`). No Django generic editing views (ListView/FormView/CreateView) — the existing repo style is a hand-rolled plain `View`.

## Spec check (per project rule `updatelogics`)

Searched [`docs/specs/`](../docs/specs/) — feature/operation specs document **behavior** (URLs, validation, ledger effects), not view implementation style. No spec mandates FBV or CBV. **This is a pure behavior-preserving refactor**; all specs' behavior must be kept identical.

## Blast radius (verified)

- Tests and UI tests reference views **only by URL name** via `reverse("...")` / `self.goto("...")`. URL `name=` values must stay unchanged.
- Direct references to FBV names exist only in:
  - each app's `views.py`/`views/` module itself,
  - the package `views/__init__.py` export lists,
  - each app's `urls.py` (`views.<fn>` → must become `views.<Cls>.as_view()`).
- No test or management command imports view functions directly.

## Conversion recipe (apply to every FBV)

1. Rename `def foo_view(request, pk):` → `class FooView(View):` in the same module.
2. Extract the POST branch into `def post(self, request, *args, **kwargs)` and the GET branch into `def get(self, request, *args, **kwargs)`. URL kwargs (`pk`, `entity_pk`, etc.) are read from `self.kwargs` / method `**kwargs`.
3. Move shared pre-branch setup (object loading, guards, logging) into a `_setup(self, request)` helper (mirroring `OperationCreateView._setup_view` at [`base.py:86`](../apps/app_operation/views/create_operation/base.py:86)), called at the top of both `get` and `post`, or from `dispatch` when it must short-circuit.
4. Convert request-taking helper functions into private methods (`self._helper(...)`). Keep **pure** (no-`request`) helpers at module level (the existing pattern: `_compute_amount`, `_build_formset` in `base.py`).
5. Preserve **all** `messages.*`, audit/log lines, redirect targets, template names, and HTTP status codes exactly.
6. Auth: FBVs decorated with `@login_required` get a `LoginRequiredViewMixin` or `@method_decorator(login_required, name="dispatch")` on the class. HTTP-method gating (`@require_http_methods([...])`) is replaced naturally: a plain `View` that defines only `get` returns 405 for other methods (equivalent behavior).
7. Update the package `views/__init__.py` to export the **class** names and refresh `__all__`.
8. Update `urls.py`: `views.<fn>` → `views.<Cls>.as_view()`. Keep `name=` identical.
9. Run the app's targeted tests (see Verification).

## Naming convention

`foo_bar_view` / `foo_bar` → `FooBarView` (matches `OperationCreateView`, `BirthCreateView`). Where an FBV is a thin wrapper over a shared base (e.g. `add_vendor_view`), convert to a small `View` subclass setting a class attribute (e.g. `role_type`) and let the base class do the work.

## View inventory & conversion mapping

### Tier 1 — app_base (2)
| FBV | CBV | Methods |
|---|---|---|
| `profile` ([`views.py:18`](../apps/app_base/views.py:18)) | `ProfileView` | GET |
| `profile_edit` ([`views.py:24`](../apps/app_base/views.py:24)) | `ProfileEditView` | GET/POST |

URLs: [`apps/app_base/urls.py`](../apps/app_base/urls.py) → `.as_view()`.

### Tier 2 — app_report (5) — all `@login_required`
File: [`apps/app_report/views.py`](../apps/app_report/views.py)
| FBV | CBV | Methods |
|---|---|---|
| `reports_hub_view` (52) | `ReportsHubView` | GET |
| `income_statement_view` (61) | `IncomeStatementView` | GET |
| `balance_sheet_view` (74) | `BalanceSheetView` | GET |
| `cash_flow_view` (87) | `CashFlowView` | GET |
| `equity_statement_view` (96) | `EquityStatementView` | GET |

Helpers `_resolve` (17) and `_base_context` (41) → private methods. URLs: [`apps/app_report/urls.py`](../apps/app_report/urls.py).

### Tier 3 — app_transaction (5)
File: [`apps/app_transaction/views.py`](../apps/app_transaction/views.py)
| FBV | CBV | Methods |
|---|---|---|
| `entity_payment_transactions_view` (19) | `EntityPaymentTransactionsView` | GET |
| `entity_payables_view` (260) | `EntityPayablesView` | GET |
| `entity_receivables_view` (273) | `EntityReceivablesView` | GET |
| `transaction_detail_view` (286) | `TransactionDetailView` | GET |
| `transaction_reverse_view` (318) | `TransactionReverseView` | GET/POST |

Helpers `_build_obligation_transactions` (98), `_obligation_context` (157) → private methods. URLs: [`apps/app_transaction/urls.py`](../apps/app_transaction/urls.py).

### Tier 4 — app_entity (13; setup wizard excluded)
Files under [`apps/app_entity/views/`](../apps/app_entity/views/)
| File | FBV | CBV | Methods |
|---|---|---|---|
| `entity_list.py` | `entity_list_view` | `EntityListView` | GET |
| `entity_detail.py` | `entity_detail_view` | `EntityDetailView` | GET |
| `person_create.py` | `person_create_view` | `PersonCreateView` | GET/POST |
| `person_edit.py` | `person_edit_view` | `PersonEditView` | GET/POST |
| `project_edit.py` | `project_edit_view` | `ProjectEditView` | GET/POST |
| `add_contact_info.py` | `add_contact_info_view` | `AddContactInfoView` | GET/POST |
| `edit_contact_info.py` | `edit_contact_info_view` | `EditContactInfoView` | GET/POST |
| `add_stakeholder.py` | `add_stakeholder_base` + `add_{vendor,client,worker,shareholder}_view` | `AddStakeholderView` base + `AddVendorView`, `AddClientView`, `AddWorkerView`, `AddShareholderView` (each sets `role_type`) | GET/POST |
| `edit_stakeholder.py` | `edit_stakeholder_view` | `EditStakeholderView` | GET/POST |
| `category/category_bulk_assign.py` | `category_bulk_assign_view` | `CategoryBulkAssignView` | GET/POST |
| `category/category_relation_detail.py` | `category_relation_detail_view` | `CategoryRelationDetailView` | GET |
| `category/category_relation_edit.py` | `category_relation_edit_view` | `CategoryRelationEditView` | GET/POST |
| `project_setup_wizard.py` | **EXCLUDED** | — | — |

URLs: [`apps/app_entity/urls.py`](../apps/app_entity/urls.py) (setup wizard entries stay as FBV references).

### Tier 5 — app_inventory (14)
File: [`apps/app_inventory/views.py`](../apps/app_inventory/views.py)
| FBV | CBV | Methods |
|---|---|---|
| `stock_detail` (40) | `StockDetailView` | GET |
| `stock_history` (153) | `StockHistoryView` | GET |
| `quick_consume` (343) | `QuickConsumeView` | GET(redirect)/POST |
| `product_detail` (435) | `ProductDetailView` | GET |
| `project_product_templates_setup` (460) | `ProjectProductTemplatesSetupView` | GET/POST |
| `product_template_detail` (509) | `ProductTemplateDetailView` | GET |
| `entity_product_templates_list` (535) | `EntityProductTemplatesListView` | GET |
| `create_product_template` (555) | `CreateProductTemplateView` | GET/POST |
| `create_purchase_movement` (596) | `CreatePurchaseMovementView` | GET/POST |
| `create_sale_movement` (611) | `CreateSaleMovementView` | GET/POST |
| `create_inventory_movement` (623) | `CreateInventoryMovementRedirectView` | GET (shim redirect) |
| `reverse_inventory_movement_line` (768) | `ReverseInventoryMovementLineView` | POST |
| `batch_reverse_inventory_movement_lines` (807) | `BatchReverseInventoryMovementLinesView` | POST |
| `register_deferred_movements` (858) | `RegisterDeferredMovementsView` | POST |

Helpers `_consume_error_redirect`, `_parse_consume_input`, `_build_consume_raw_post`, `_render_movement_form`, `_create_inventory_movement` → private methods. URLs: [`apps/app_inventory/urls.py`](../apps/app_inventory/urls.py).

### Tier 6 — app_operation (17; wizards & already-CBV excluded)
Files under [`apps/app_operation/views/`](../apps/app_operation/views/)
| File | FBV | CBV | Methods |
|---|---|---|---|
| `adjustment.py` | `record_accounting_adjustment` (79) | `RecordAccountingAdjustmentView` | GET/POST |
| `adjustment.py` | `record_item_adjustment` (176) | `RecordItemAdjustmentView` | GET/POST |
| `adjustment.py` | `reverse_adjustment` (299) | `ReverseAdjustmentView` | GET/POST |
| `adjustment.py` | `reverse_item_adjustment` (377) | `ReverseItemAdjustmentView` | GET/POST |
| `adjustments_list.py` | `adjustments_list_view` | `AdjustmentsListView` | GET |
| `detail.py` | `operation_detail_view` (55) | `OperationDetailView` | GET |
| `edit.py` | `operation_update_view` (11) | `OperationUpdateView` | GET/POST |
| `invoice_items.py` | `invoice_items_list_view` (13) | `InvoiceItemsListView` | GET |
| `list.py` | `operation_list_view` (14) | `OperationListView` | GET |
| `period.py` | `period_detail_view` (19) | `PeriodDetailView` | GET |
| `period.py` | `period_list_view` (46) | `PeriodListView` | GET |
| `period.py` | `period_close_view` (82) | `PeriodCloseView` | GET/POST |
| `period.py` | `period_ledger_view` (164) | `PeriodLedgerView` | GET |
| `record_transaction.py` | `record_transaction_payment` (111) | `RecordTransactionPaymentView` | GET/POST |
| `record_transaction.py` | `record_transaction_repayment` (155) | `RecordTransactionRepaymentView` | GET/POST |
| `reverse.py` | `operation_reverse_view` (12) | `OperationReverseView` | GET/POST |

Helpers `_render_transaction_form` (16), `_process_transaction` (34) in `record_transaction.py` → private methods. URLs: [`apps/app_operation/urls.py`](../apps/app_operation/urls.py) (wizard entries stay as FBV references).

## Execution order — phased, with review gate (per user decision)

**Risk-reduction decision**: convert the lower-risk apps first, **review before** touching the higher-risk action-heavy apps. Each app is converted and its targeted tests verified before moving on.

### Phase A — low/mid risk (Tiers 1–4)
1. `app_base` (2 views)
2. `app_report` (5 GET-only views)
3. `app_transaction` (5 views)
4. `app_entity` (13 views, excludes `project_setup_wizard`)

### ⛔ REVIEW GATE
Present converted Phase A views for user review before proceeding. Do **not** start Phase B until approved.

### Phase B — higher risk (Tiers 5–6, action/movement/ledger POST flows)
5. `app_inventory` (14 views)
6. `app_operation` (17 views, excludes wizards & already-CBV)

### Phase C — full verification & commit
7. Run full test suite, fix regressions, delete temp log.
8. Commit.

## Verification

Per project rules ([`AGENTS.md`](../AGENTS.md), `.roo/rules/testing.md`):

- `python manage.py check`
- Targeted tests per app, e.g. `python manage.py test app_inventory.tests.test_views_get_stock_detail_view` etc.
- Full suite: `python manage.py test --parallel=10 --keepdb` (or without `--keepdb` once after schema-affecting changes — none expected here).
- Capture full output to `tmp/<refactor>.log`, inspect, then delete the temp file.
- Do **not** run `ui_tests` unless asked.

## Risks & mitigations

- **Behavior drift**: preserve status codes (400/404/405/redirects), message texts, log/audit lines. The test suite is the safety net.
- **Auth behavior**: `@login_required` FBVs must keep redirecting anonymous users — apply the mixin/decorator correctly.
- **405 vs current behavior**: plain `View` with only `get` returns 405 on POST — matches `@require_http_methods(["GET"])`. Any FBV that *redirects* instead of 405 on the "wrong" method (e.g. `quick_consume` GET→redirect) must replicate that explicitly.
- **Stakeholder views**: the 4 thin wrappers must remain separate named classes/URLs (`add_vendor`, `add_client`, `add_worker`, `add_shareholder`); do not collapse them.
- **Wizards untouched**: do not refactor `sale_wizard_view`, `purchase_wizard_view`, or `project_setup_wizard_view`; their helpers (`_load_project`, `SALE_WIZARD`, `PURCHASE_WIZARD`) stay as-is.
- **Name collisions**: keep CBV class names unique within each package's `__init__.py` export namespace.

## Implementation status (2026-09-01)

Phase A (approved at the review gate) and Phase B are fully implemented. All conversions used plain `django.views.View` with explicit `get`/`post`/`dispatch`, preserving URL names, templates, status codes, messages, and log/audit lines.

**Converted (56 FBVs → CBVs):**
- `app_base` (2): `ProfileView`, `ProfileEditView`
- `app_report` (5): `ReportsHubView`, `IncomeStatementView`, `BalanceSheetView`, `CashFlowView`, `EquityStatementView` (shared `_ReportBaseView(LoginRequiredMixin, View)`)
- `app_transaction` (5): `EntityPaymentTransactionsView`, `EntityPayablesView`, `EntityReceivablesView` (shared `_ObligationListView`), `TransactionDetailView`, `TransactionReverseView`
- `app_entity` (13): `EntityListView`, `EntityDetailView`, `PersonCreateView`, `PersonEditView`, `ProjectEditView`, `AddContactInfoView`, `EditContactInfoView`, `AddStakeholderView` + `AddVendorView`/`AddClientView`/`AddWorkerView`/`AddShareholderView`, `EditStakeholderView`, `CategoryBulkAssignView`, `CategoryRelationDetailView`, `CategoryRelationEditView`
- `app_inventory` (14): `StockDetailView`, `StockHistoryView`, `QuickConsumeView`, `ProductDetailView`, `ProjectProductTemplatesSetupView`, `ProductTemplateDetailView`, `EntityProductTemplatesListView`, `CreateProductTemplateView`, `_InventoryMovementCreateView` base + `CreatePurchaseMovementView`/`CreateSaleMovementView`, `CreateInventoryMovementRedirectView`, `ReverseInventoryMovementLineView`, `BatchReverseInventoryMovementLinesView`, `RegisterDeferredMovementsView`
- `app_operation` (17): `RecordAccountingAdjustmentView`, `RecordItemAdjustmentView`, `ReverseAdjustmentView`, `ReverseItemAdjustmentView`, `AdjustmentsListView`, `OperationDetailView`, `OperationUpdateView`, `InvoiceItemsListView`, `OperationListView`, `PeriodDetailView`, `PeriodListView`, `PeriodCloseView`, `PeriodLedgerView`, `_TransactionRecordView` base + `RecordTransactionPaymentView`/`RecordTransactionRepaymentView`, `OperationReverseView`

**Notes:**
- Shared pre-branch setup moved into `_setup(self, ...)` helpers returning `(obj, response)` (or 3-tuples) so GET/POST short-circuit on guards/redirects; `assert x is not None` used for type narrowing.
- Pure (no-`request`) helpers kept at module level (`_stock_portfolio_rows`, `_build_consume_raw_post`, `_build_obligation_transactions`, `_build_adjustment_type_data`, `parse_item_changes`, `_build_navigation_overrides`, `_compute_amount`/`_build_formset` unchanged).
- `@login_required` → `LoginRequiredMixin`; `@require_http_methods` → natural 405 from plain `View` (equivalent).
- Reversal-style views (transaction/operation/adjustment reverses) keep one `_handle()` shared by `get`/`post` to preserve the exact GET-confirm/POST-execute flow.
- Left as FBVs per scope: `project_setup_wizard_view`, sale/purchase wizards, `farm/views.py` error handlers. Already-CBV views (`LoginView`, `OperationCreateView`, `BirthCreateView`, `DeathCreateView`, `EvaluationCreateView`) unchanged.

**Verification:**
- `manage.py check` — no issues.
- Per-app suites: app_base+app_report+app_transaction (111), app_entity (85), app_inventory (182), app_operation (1002) — all OK.
- Full `apps.*` suite: **1460 tests, OK** (`manage.py test apps --parallel=10 --keepdb`).
- `ui_tests/` (Selenium) are not part of the standard suite and were not run for verification.
