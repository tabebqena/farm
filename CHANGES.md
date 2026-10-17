# Changelog

All notable changes to the **farm** project are documented in this file.

The project is a Django-based financial management platform for a livestock farm
business. It tracks money flowing between **Entities** (people, projects, vendors,
clients) through **Operations** (business events) that generate **Transactions**
(ledger entries) against **Funds** (each entity's wallet), with supporting models for
invoices, adjustments, inventory, and evaluations.

Dates follow the commit history (`git log`). The format is loosely based on
[Keep a Changelog](https://keepachangelog.com/en/1.0.0/). The current release version
is tracked in the [`VERSION`](VERSION) file (semantic versioning).


---


## 2026-10-17 — Fix tag collision when a purchase line has multiple heads

### Fixed
- Submitting a purchase whose invoice has a bulk individually-tracked line
  (quantity > 1) alongside another line of the same template no longer aborts
  with `Constraint "unique_product_tag_per_entity" is violated.` Each line
  stores a single tag, but the extra heads were auto-numbered by
  `ProductTemplate.next_tag` with no knowledge of the tags the *other* lines
  would use, so a later line could claim a tag an earlier line had already
  generated. `create_from_session` now collects every line's explicit tag and
  passes it as a reserved set through
  `InventoryMovementLine.create_received_movement_lines` →
  `Product.objects` lazy creation → `create_products_for_item` → `next_tag`, so
  auto-generated heads skip tags reserved for sibling lines.

### Tests
- `PurchaseCreateFromSessionTest.test_create_from_session_bulk_line_does_not_steal_sibling_tag`.


## 2026-10-17 — Fix false duplicate-tag error in the purchase wizard

### Fixed
- Adding a second invoice line for the same individually-tracked (tagged)
  template with a blank **Tag / ID** no longer fails with *"This Tag/ID is
  already used by another item."* The wizard auto-suggests tags via
  `ProductTemplate.next_tag`, which only looked at already-persisted `Product`
  rows; since the wizard keeps pending lines in the session, both lines were
  suggested the same tag (`CALF1`) and the duplicate guard rejected the second.
  `next_tag` now accepts a `reserved` set of pending tags and skips them, and
  the add-item view passes the other session lines' tags through. Explicitly
  user-typed duplicates are still rejected.

### Changed
- The purchase wizard's add-item form now **prefills** the Tag / ID with the
  next available tag (derived from existing stock plus the lines already added
  to the invoice) instead of leaving it blank and assigning it invisibly on
  submit.


## 2026-10-17 — Hide fund balance for World, System and external entities

### Changed
- Added `Entity.shows_balance` (`not is_virtual and is_internal`): real internal
  funds only. Virtual (World/System) and external (non-internal) funds have no
  enforceable balance, so it is now hidden in the entity list (table + mobile
  card) and in operations (operation-list header and the create-form
  `fund-balance.html` snippet). The balance is still shown on the entity detail
  page and payment-transactions ledger.


## 2026-10-17 — Fix 500 on pages whose fund-balance include omits the currency

### Fixed
- `snippets/create-form/fund-balance.html` passed `fund_currency` as a filter
  argument; when the including template (purchase/sale wizard and invoice pages)
  did not supply it, template resolution raised `VariableDoesNotExist` → HTTP
  500. Now resolved with `{% firstof fund_currency currency as fund_symbol %}`,
  falling back to the global currency.


## 2026-10-17 — Space between currency symbol and amount

### Changed
- The `money`/`money_signed` filters and `FarmMoney.format` now render a space
  between the currency symbol and the figure (`E£ 1,234.56`) for readability;
  `money_plain` is unchanged. Zero-value placeholders in adjustment forms follow.


## 2026-10-17 — Fix production Bad Gateway (static manifest)

### Fixed
- In production (`DEBUG=0`) the container entrypoint aborted: WhiteNoise's
  `CompressedManifestStaticFilesStorage` failed `collectstatic` because the
  vendored `imask.min.js` referenced a missing `imask.min.js.map`. The dangling
  `//# sourceMappingURL=imask.min.js.map` comment was removed, so `collectstatic`
  completes and gunicorn starts (no more 502 Bad Gateway behind the proxy).


## 2026-10-17 — Unified money display (grouping, symbol, alignment)

Every read-only monetary amount now renders through one formatter so figures
show a currency symbol, thousands grouping and 2 decimals consistently, instead
of the previous mix of `floatformat:2`, raw `Decimal.__str__` and hand-built
`"$ " + x.toFixed(2)` strings. Quantities/counts are untouched.

### Added
- `apps/app_base/templatetags/money.py` with `money`, `money_plain` and
  `money_signed` filters (`{{ v|money }}` → `E£1,234.56`; `money_plain` without
  the symbol; `money_signed` forces `+`/`-`). Half-up rounding, 0 for
  `None`/blank/invalid, optional symbol override.
- `static/js/money.js` exposing `window.FarmMoney` (`format`, `signed`, `plain`)
  mirroring the server filter for client-side totals.
- `apps.app_base.context_processors.currency` (registered in
  `TEMPLATES`) so `{{ currency }}` is global and `<body data-currency>` feeds JS.
- `.money` CSS utility (tabular figures, forced LTR) in `static/css/main.css`.
- `apps/app_base/tests/test_money_filter.py`.

### Changed
- Default `CURRENCY_SYMBOL` is now the Egyptian pound (`E£`); hardcoded `$`
  input-group prefixes and `$0.00` seed values now render `{{ currency }}`.
- Migrated all money displays to `|money` / `FarmMoney`: reports
  (`balance_sheet`, `cash_flow`, `equity_statement`, `income_statement`), entity
  pages, operation list/detail/period/invoice/wizard snippets, adjustments, and
  transaction ledgers. JS totals in `operation-formset.js`,
  `partial-payment-subform.js`, `record_adjustment.html`,
  `record_item_adjustment.html` and `evaluation_form.html` use `FarmMoney`.

### Fixed
- `entity_detail.html` used a non-existent `entity.currency` (always `$`);
  `entity_list.html` showed balances with no symbol; reports showed no currency
  symbol; several templates printed raw `Decimal` values without 2 decimals or
  grouping.


## 2026-10-17 — Money inputs rebuilt on IMask

All operation amount/quantity inputs now use the **IMask** number mask instead of
the bespoke `AmountInputFormatter`. Formatting and caret handling are delegated to
IMask's model/view engine, which tracks the caret by digit, so typing across the
decimal point no longer forces the cursor back to the integer part. The visible +
hidden input twin architecture, `+`/`−` steppers, and Arrow Up/Down stepping are
preserved. Amount fields are now larger (tabular figures) and force a left-to-right
numeric direction even under the Arabic RTL layout; thousands are grouped by three.

### Added
- `static/js/vendor/imask.min.js` (IMask 7.6.1, MIT) plus licence/README.
- `static/js/amount-input.js` exposing `window.AmountInput` with
  `getValue()`, `getNumber()`, `setValue()`, and `getInstance()` helpers used by
  the other scripts.

### Changed
- `templates/base.html` loads `vendor/imask.min.js` then `js/amount-input.js`;
  removed `static/js/amount-input-formatter.js`.
- `static/js/operation-formset.js` and `static/js/partial-payment-subform.js` read
  and write amounts through `window.AmountInput` (fixes values ≥ 1000 being parsed
  as their integer prefix).
- `add_payment_form.html` and `evaluation_form.html` inline scripts use the new
  helpers.
- `static/css/main.css`: larger amount font (`--amount-font-size`, default 1.4rem),
  tabular figures, `direction: ltr` for the numeric field, and logical-property
  radii for the stepper buttons.
- `ui_tests/base.py::fill_amount` drives `AmountInput.setValue`.

### Fixed
- Caret no longer jumps while editing; the decimal part can be typed continuously.
- Amount inputs render correctly in Arabic (RTL) mode.
- Thousands separators are shown while typing and for pre-filled values.


## 2026-10-17 — Purchase from the World (ad-hoc, fully settled)

The **World** entity can now act as a vendor on a **Purchase** without a
Stakeholder record, so a one-off purchase from an unregistered party can be
recorded without minting a throw-away entity. A World purchase is an ad-hoc,
fully-settled one-off: it is paid in full at creation, its payment cannot be
reversed on its own, and it cannot be adjusted.

### Added
- `Operation.counterparty_is_world` — the single predicate driving the World
  rules (Purchase → destination is World).
- World is always offered in the purchase wizard's vendor picker for every
  project (`PurchaseWizardStep1Form`, `PurchaseOperation.get_related_entities`),
  even when the project has no vendor Stakeholders.
- `is_vendor_or_world` transaction-type predicate for the `PURCHASE_*` types
  (`_TX_ENTITY_TYPE_MAP`).

### Changed
- `PurchaseOperation.clean_destination()` accepts the World without an active
  VENDOR Stakeholder (all other destinations keep the strict validation).
- `PurchaseOperation.create_from_session()` requires `amount_paid == total` when
  the vendor is the World; `Operation.process_payment()` and
  `LinkedPaymentTransactionMixin.create_payment_transaction()` enforce full
  settlement for a World counterparty.
- The purchase wizard no longer hard-blocks a project with no vendors; step 3
  rejects a partial/zero payment when the counterparty is the World.
- World purchases reverse issuance + payment together
  (`PurchaseOperation._implicit_reversable_transaction_types`); a standalone
  `PURCHASE_PAYMENT` reversal is blocked in `transaction_reverse_view` and hidden
  by `TransactionDetailView.can_reverse`.
- Accounting and invoice-item adjustments are rejected on a World purchase
  (`Adjustment.clean()`, `InvoiceItemAdjustment.clean()`, both adjustment views,
  and the adjustment action buttons in the detail templates).

### Tests
- New purchase-from-World suite: acceptance, full-settlement enforcement,
  reversal (issuance + payment), standalone-payment-reversal block, no-vendor
  wizard access, and adjustment block
  (`app_operation.tests.operations.purchase.test_purchase_world`).
- Existing purchase, adjustment and transaction suites stay green.

---


## 2026-10-17 — Make soft deletes work from Django admin; operations own their transactions

Two soft-delete defects made admin cleanup impossible. First, Django admin
decided deletes with its raw `PROTECT` collector, which sees every row —
soft-deleted tombstones included — so **no entity could be deleted from admin**
at all (its auto-created `FinancialPeriod` blocked the confirmation page, and
tombstoned operations / periods / stakeholders were listed as protected).
Second, deleting an `Operation` left its ledger `Transaction`s live (they attach
via a `GenericForeignKey`, invisible to the delete guard), so the transactions
kept blocking the entity after the operation was gone.

### Added
- [`SoftDeleteAdminGuardMixin`](apps/app_base/admin_guard.py) — re-points the
  admin delete decision at `BaseModel.get_delete_blockers()` instead of the DB
  collector: tombstones and `_delete_auto_relations` rows stop blocking, live
  financial dependents are still refused (with the guard's message), and a guard
  `ValidationError` is shown as an admin error instead of a 500. Applied to the
  `Entity`, `Stakeholder`, `Operation`, `FinancialPeriod`, `Transaction`,
  `Adjustment`, `ProductTemplate`, `Product`, `ProductCapitalValuation` and
  `MedicalRecord` admins.
- [`BaseModel._before_soft_delete()`](apps/app_base/models.py) — a hook that
  runs after the guard passes and after owned auto-relations are soft-deleted,
  for children the reverse-relation scan cannot see.

### Changed
- [`HasRelatedTransactions._before_soft_delete()`](apps/app_base/mixins.py)
  soft-deletes a record's ledger transactions with it (reversal mirrors first).
  This covers `Operation` (and every proxy) and `Adjustment`: their transactions
  no longer survive as live orphans blocking their entities, so leaf-up deletion
  (delete operations/adjustments → delete entity) works.

### Tests
- Operation delete soft-deletes linked transactions, unblocks its entity, and
  orders reversal mirrors first
  (`app_operation.tests.test_operation_soft_delete`).
- Adjustment delete soft-deletes its transaction
  (`app_adjustment.tests.test_adjustment_adjustment_transaction`).
- Admin deletes: bare entity deletable, tombstoned owned rows no longer block,
  live operations still block, guard errors surfaced as messages, and entity
  deletable after deleting the operation via admin
  (`app_entity.tests.test_admin_delete`).

---


## 2026-10-17 — Entity start date drives the first financial period

Person and project creation now accept a **Start Date** (defaulting to today).
The date is stored on `Entity.start_date`, and the open `FinancialPeriod`
auto-created on activation starts from it (falling back to the creation date
when unset). Future start dates are rejected.

### Added
- Start Date field on the person create form (`PersonForm`) and the project
  setup wizard step 1; the chosen date is persisted as `Entity.start_date` and
  seeds the entity's first financial period.

### Changed
- `Entity.save()` now seeds the first `FinancialPeriod.start_date` from
  `Entity.start_date` when present (creation date fallback otherwise).
- `Entity.clean()`, `PersonForm.clean_start_date()` and the wizard step 1
  reject start dates later than today.

### Tests
- Person create: submitted/default start date and future-date rejection
  (`app_entity.tests.test_entity_forms_person_create_view`).
- Wizard step 1: default/submitted start date and future-date rejection
  (`app_entity.tests.test_project_setup_wizard_project_setup_wizard_step1`).
- Wizard integration: start date drives entity + first period
  (`app_entity.tests.test_project_setup_wizard_project_setup_wizard_integration`).
- Model guard: future `start_date` rejected
  (`app_operation.tests.period.test_financial_period_entity_period_auto_create`).


## 2026-10-17 — Production readiness: env-driven settings, container image, secure defaults

The project is no longer development-only. All deployment-specific values now
come from the environment (with a `.env` file for local use), production
defaults are secure, static files are served by WhiteNoise, and a Docker
image/compose stack plus a health probe make it runnable behind a reverse
proxy.

### Added
- [`.env.example`](.env.example) — documented template for every environment
  variable (secret, hosts, database URL, security, email, logging). Copy to
  `.env` (git-ignored).
- [`Dockerfile`](Dockerfile), [`docker-compose.yml`](docker-compose.yml),
  [`docker/entrypoint.sh`](docker/entrypoint.sh),
  [`docker/gunicorn.conf.py`](docker/gunicorn.conf.py) and
  [`.dockerignore`](.dockerignore) — non-root Gunicorn image; the entrypoint
  runs `migrate` + `collectstatic` before boot. Compose persists the SQLite DB,
  media, static and logs in named volumes.
- [`requirements-dev.txt`](requirements-dev.txt) — dev/test/tooling
  dependencies; [`requirements.txt`](requirements.txt) now carries only the
  production runtime (`Django`, `gunicorn`, `whitenoise`, `psycopg[binary]`,
  `asgiref`, `sqlparse`, `typing_extensions`).
- `/healthz/` liveness endpoint ([`farm/views.py`](farm/views.py),
  [`farm/urls.py`](farm/urls.py)) — unauthenticated, never SSL-redirected
  (`SECURE_REDIRECT_EXEMPT`), used by the image `HEALTHCHECK` and orchestrators.
- [`test_health.py`](apps/app_base/tests/test_health.py).

### Changed
- [`farm/settings.py`](farm/settings.py) — env-driven configuration:
  - `DJANGO_SECRET_KEY` (required unless `DEBUG`), `DJANGO_DEBUG` (default
    **False**, `True` only under tests), `DJANGO_ALLOWED_HOSTS`,
    `DJANGO_CSRF_TRUSTED_ORIGINS`.
  - `DJANGO_DATABASE_URL` parsed for `sqlite://` / `postgres://` (SQLite file
    remains the fallback); `DJANGO_STATIC_ROOT`, `DJANGO_MEDIA_ROOT`.
  - Secure-by-default production settings: SSL redirect, secure/HSTS cookies,
    HSTS (1 year), `X_FRAME_OPTIONS=DENY`, content-type nosniff, referrer
    policy, and `SECURE_PROXY_SSL_HEADER`.
  - `STATIC_ROOT` + WhiteNoise `CompressedManifestStaticFilesStorage` when not
    `DEBUG`; WhiteNoise middleware is only installed outside `DEBUG`.
  - Configurable log levels, plus `mail_admins` error email when `ADMINS` is set.
- [`requirements.txt`](requirements.txt) — trimmed to production runtime.
- [`.gitignore`](.gitignore) — ignores `.env`, `staticfiles/` and `media/`.
- [`docs.py`](docs.py) — the docs build defaults `DJANGO_DEBUG=1` so tooling
  works without a configured environment.

### Verification
- `manage.py check` and `manage.py check --deploy` are clean with production
  environment variables.
- `collectstatic` produces the WhiteNoise manifest (141 files, 413
  post-processed).
- Gunicorn smoke test: `/healthz/` returns `200` while other routes redirect.
- Full suite **1,542 tests OK** (`manage.py test apps --parallel=10 --keepdb`).

### Deploying
```
cp .env.example .env          # set DJANGO_SECRET_KEY (+ hosts, admins)
docker compose up --build -d  # http://localhost:8000
python -c "import secrets; print(secrets.token_urlsafe(64))"  # secret generator
```
Terminate TLS at a reverse proxy and keep `DJANGO_SECURE_SSL_REDIRECT=1`; set it
to `0` only for a plain-HTTP local smoke test.


---

## 2026-10-17 — Deployment helper script

### Added
- [`scripts/deploy.sh`](scripts/deploy.sh) — prompts for the SSH username and
  password, then logs into the host, pulls the latest `main` (cloning the repo
  if missing) and rebuilds/recreates the docker compose stack. Host, app dir,
  branch, repo URL and compose command are overridable via `FARM_*` environment
  variables; it refuses to deploy if `.env` is missing.

---

## 2026-10-17 — Action provenance: "What happened & why" tracing

A new `app_audit` app records, for every mutating request, the user's submitted
input and every model save it caused — including the full *new shape* of each
row — and tags the rows the app creates automatically with the rule that
explains *why*. This lets an officer see what the app did under the hood
(transactions, movements, periods, valuations, reversals, lazy products) and
decide whether an unexpected entry came from their input or from the app,
instead of blindly soft-deleting and re-entering.

### Added
- New app [`apps/app_audit`](apps/app_audit) with two append-only models:
  [`ActionTrace`](apps/app_audit/models.py) (one per mutating request: actor,
  method/path, sanitized `payload`, status, error, root record, duration) and
  [`SaveLog`](apps/app_audit/models.py) (one per `BaseModel.save()`: record ref,
  kind, `new_shape`, and — for auto-created rows — `is_derived`, `role`,
  `reason_code`, `reason_text`). Both subclass plain `models.Model` on purpose
  (infrastructure rows: never soft-deleted, never tracked by themselves).
- [`apps/app_audit/context.py`](apps/app_audit/context.py) — request-scoped
  provenance runtime (contextvars): `start_trace` / `finish_trace`,
  `record_save`, `derived(role, reason)` and `record_validation_error`.
  No-op when `FARM_TRACKING_ENABLED` is off or when no trace is active.
- [`apps/app_audit/serialization.py`](apps/app_audit/serialization.py) —
  `serialize_instance()` builds the JSON-safe *new shape* of a row (FKs as
  `{model, pk}`, datetimes ISO, decimals/UUIDs as strings; never raises).
- [`apps/app_audit/reasons.py`](apps/app_audit/reasons.py) — the role/reason
  catalog mapping each auto-creation rule to a plain-language explanation,
  cross-referenced by the operation specs under `docs/`.
- [`apps/app_audit/middleware.py`](apps/app_audit/middleware.py) —
  `ActionTraceMiddleware` opens one trace per mutating request (committed
  independently so failures are still recorded) and closes it with the outcome.
- [`apps/app_audit/views.py`](apps/app_audit/views.py) + templates —
  `/audit/` Activity list (filter by user/status/action/date), the
  `/audit/trace/<id>/` detail page (level 1 *your input*, level 2 *auto-created
  rows + why*, level 3 *every save* with its new shape), and
  `/audit/record/<app>/<model>/<id>/` ("why does this row exist?").
- `manage.py purge_savelogs` — physically trims the append-only trail
  (`--older-than`, `--before`, `--trace`, `--level {all,derived-only}`,
  `--model`, `--keep-traces`, `--batch-size`, `--dry-run`); by default also
  removes traces left with no saves.
- [`audit_tags.py`](apps/app_audit/templatetags/audit_tags.py) —
  `{% record_history_url obj %}`; the "History / Why?" link is added to the
  operation, entity and product detail pages.
- `FARM_TRACKING_ENABLED` setting (default `True`; forced off under
  `manage.py test`, overridable per test).

### Changed
- [`apps/app_base/models.py`](apps/app_base/models.py) — `BaseModel.save()` now
  records each write through `_record_provenance()`; `_perform_soft_delete()`
  passes `provenance_kind="soft_delete"` so the tombstone is logged as such.
- Auto-creation paths now tag their rows via `provenance.derived(...)`:
  `create_issuance_transaction` / `create_payment_transaction` /
  `create_repayment_transaction` ([`mixins.py`](apps/app_base/mixins.py)),
  birth/death/consumption inventory movements
  ([`operation.py`](apps/app_operation/models/operation.py)) and lazy products
  ([`app_inventory/models.py`](apps/app_inventory/models.py)), entity period
  create/close ([`app_entity/models/__init__.py`](apps/app_entity/models/__init__.py)),
  capital valuations ([`op_capital_valuation.py`](apps/app_operation/models/proxies/op_capital_valuation.py))
  and reversals ([`app_base/models.py`](apps/app_base/models.py),
  [`app_transaction/models.py`](apps/app_transaction/models.py)).
- [`navigation.py`](apps/app_base/navigation.py) — Activity / Action Trace /
  Record History entries; [`farm/urls.py`](farm/urls.py) mounts `/audit/`.


## 2026-09-04 — Category filtering is expense-only; drop `category_required` and `category_type`

The financial-category feature is now scoped to the **Expense** operation only, and
its configuration is reduced to a single source of truth: `has_category`. A proxy
that declares `has_category = True` (only `ExpenseOperation`) shows a **required**
category dropdown listing the active `FinancialCategory` rows **linked to the URL
project entity** — no other operation exposes or stores a category.

### Changed
- [`apps/app_operation/models/operation.py`](apps/app_operation/models/operation.py) —
  removed the `category_required` class flag (it duplicated `has_category`) and the
  `category_type` class attribute. [`Operation.clean()`](apps/app_operation/models/operation.py)
  now rejects an operation without a category whenever `has_category` is set; the
  category-type mismatch guard was removed. The `resolve_request()` config dict and
  the `StockEventMixin` defaults only carry `has_category`.
- [`apps/app_operation/models/proxies/op_expense.py`](apps/app_operation/models/proxies/op_expense.py) —
  keeps `has_category = True`; dropped its `category_required` / `category_type`
  overrides. [`op_loan.py`](apps/app_operation/models/proxies/op_loan.py),
  [`op_sale.py`](apps/app_operation/models/proxies/op_sale.py) and
  [`op_purchase.py`](apps/app_operation/models/proxies/op_purchase.py) dropped their
  redundant `category_required = False` / `category_type` namespaces.
- [`apps/app_entity/models/category.py`](apps/app_entity/models/category.py) — removed
  the unused `FinancialCategory.category_type` field (the catalog is expense-only).
  New migration
  [`0008_remove_financialcategory_category_type.py`](apps/app_entity/migrations/0008_remove_financialcategory_category_type.py).
- [`apps/app_operation/views/create_operation/base.py`](apps/app_operation/views/create_operation/base.py) —
  the expense category dropdown lists every active category linked to the URL entity
  (no `category_type` filter).
- [`apps/app_operation/validators.py`](apps/app_operation/validators.py) — the
  required-category branch keys off `has_category`.
- [`apps/app_base/management/commands/seed.py`](apps/app_base/management/commands/seed.py) —
  removed the dead `"type": "EXPENSE"` keys from `default_categories`.
- Templates — the create-form category snippet and [`generic_form.html`](apps/app_operation/templates/app_operation/generic_form.html)
  expose the single `has_category` flag; the detail header
  ([`address_bar.html`](apps/app_operation/templates/app_operation/snippets/address_bar.html))
  now badges the chosen category name instead of the removed type; the entity
  category cards show `aspect` and no longer display the removed type.

### Removed
- Operation `category_required` and `category_type` configuration, the `category_type`
  mismatch validation branch, and the `FinancialCategory.category_type` DB field —
  together with the tests, entity/seed/category-UI code, and specs that referenced them.

### Specs
- Updated [`docs/operations/op_8_expense.md`](docs/operations/op_8_expense.md) (config
  flag, VC13, §8 UI, branch catalog, coverage matrix), the `has_category` flag rows in
  the other operation contracts, [`docs/operations/_OPERATION_SPEC_TEMPLATE.md`](docs/operations/_OPERATION_SPEC_TEMPLATE.md)
  and [`docs/entities/entity_6_financial_categories.md`](docs/entities/entity_6_financial_categories.md).

---

## 2026-09-04 — Operation config cleanup: adjustability flags single-sourced

### Changed
- [`apps/app_operation/models/operation.py`](apps/app_operation/models/operation.py) —
  removed the `can_adjust` property, which duplicated the `is_adjustable` class
  flag; accounting-adjustment eligibility now has a single source of truth
  (`is_adjustable`). The former `is_items_adjustable` class flag is now a
  property returning `has_invoice` — item adjustments apply exactly where
  invoice items exist (PURCHASE / SALE) — and the redundant per-proxy
  `is_items_adjustable` overrides were dropped (Purchase, Sale, Expense).
- [`apps/app_operation/views/adjustment.py`](apps/app_operation/views/adjustment.py) —
  the accounting-adjustment guard now checks `operation.is_adjustable` instead
  of the removed `operation.can_adjust`.
- [`apps/app_operation/tests/test_operation_mixins.py`](apps/app_operation/tests/test_operation_mixins.py) —
  added `AdjustabilityConfigTest` covering the flag/property contract.

## 2026-09-04 — Harden the one-shot `create()` payment test

### Fixed
- [`apps/app_operation/tests/operations/test_operation_create.py`](apps/app_operation/tests/operations/test_operation_create.py) —
  `CashInjectionCreateTest.test_create_without_payment_does_not_call_process_payment`
  now spies on `process_payment` (asserting it is never called for a `can_pay=False`
  proxy) and asserts the real transaction map — 1 issuance + 1 automatic one-shot
  payment — replacing the weak `pk is not None`-only check and correcting the
  misleading claim that `create()` produces no payment transaction at all.

## 2026-09-04 — Entity app primary-source contracts (`docs/entities`)

Documentation only — no code, model, migration or test changes.

### Added
- New [`docs/entities/`](docs/entities/README.md) spec tree mirroring
  `docs/operations/`: shared
  [`_ENTITY_SPEC_TEMPLATE.md`](docs/entities/_ENTITY_SPEC_TEMPLATE.md) +
  [`README.md`](docs/entities/README.md) index + one primary-source contract per
  `app_entity` area — Entity Lifecycle & Types
  ([`entity_1_lifecycle.md`](docs/entities/entity_1_lifecycle.md)), Person
  ([`entity_2_person.md`](docs/entities/entity_2_person.md)), Project & Setup
  Wizard ([`entity_3_project.md`](docs/entities/entity_3_project.md)),
  Stakeholder ([`entity_4_stakeholder.md`](docs/entities/entity_4_stakeholder.md)),
  Contact Info ([`entity_5_contact_info.md`](docs/entities/entity_5_contact_info.md)),
  Financial Categories
  ([`entity_6_financial_categories.md`](docs/entities/entity_6_financial_categories.md)).
  Each contract registers its implementing code (models → base machinery →
  consumers → views) and maps every branch to a pinning test, recording known
  coverage gaps (e.g. contact/category view tests, `max_limit` spending
  enforcement, add-flow single-primary gap).
- [`docs/README.md`](docs/README.md) — the Specifications section now links the
  live spec trees (`docs/entities/`, `docs/operations/`, `docs/features/`)
  instead of the stale `specs/...` paths.

---

## 2026-09-04 — Default the setup wizard project to act as Client & Vendor

Step 1 (Project Info) of the project setup wizard now defaults the new project
to act as **both** a Client (`is_client`) and a Vendor (`is_vendor`): the two
checkboxes render pre-checked on a fresh draft, so the created farm project can
receive invoices and charge expenses out of the box. Users can still uncheck
either option — an unchecked box stores `False` exactly as before.

### Changed
- [`apps/app_entity/views/project_setup_wizard.py`](apps/app_entity/views/project_setup_wizard.py) —
  `_default_info()` now defaults `is_vendor=True` and `is_client=True` for a
  fresh (unstarted) draft; the summary create (`_apply_create_project`) already
  applies those flags to the new project entity.

### Added
- [`apps/app_entity/tests/test_project_setup_wizard_project_setup_wizard_step1.py`](apps/app_entity/tests/test_project_setup_wizard_project_setup_wizard_step1.py) —
  `test_wizard_step_1_defaults_client_and_vendor` asserts a fresh step-1 form
  defaults both flags to `True` and renders both checkboxes checked.

---

## 2026-09-04 — Defer project creation in the setup wizard + Summary step

The project setup wizard no longer creates the project at step 1. It now collects
steps 1–6 into a session draft (no DB writes) and adds a 7th **Summary** step that
reviews everything and provides a **Create Project** button. The create action
applies the steps sequentially inside a single atomic transaction; on any failure
nothing is created and the user is redirected to the step whose data failed, with
the draft preserved so they can correct it. The wizard is now **create-only** — the
entity-pk edit/continue route (`project_setup_step`) was removed; editing an
existing project stays out of the wizard (`ProjectEditView` and the per-project
management views are unaffected).

### Changed
- [`apps/app_entity/views/project_setup_wizard.py`](apps/app_entity/views/project_setup_wizard.py) —
  rewritten as a create-only, 7-step wizard backed by a session draft
  (`project_setup_wizard` key); step handlers persist nothing; the summary create
  (`_apply_create_project`) applies the stages (project entity, categories,
  product templates, worker/vendor/shareholder stakeholders) sequentially inside
  `transaction.atomic()` and raises a per-stage error that redirects to the failing
  step; new `project_setup_cancel_view()` clears the draft.
- [`apps/app_entity/urls.py`](apps/app_entity/urls.py) — added
  `project/setup/<int:step>/` (`project_setup`) and `project/setup/cancel/`
  (`project_setup_cancel`); removed the entity-pk `project_setup_step` route.
- [`apps/app_entity/templates/app_entity/project_setup_wizard.html`](apps/app_entity/templates/app_entity/project_setup_wizard.html)
  and the `setup/step_*.html` partials — 7-step progress, create-only navigation,
  draft prefill/checked state; new `setup/step_7_summary.html` review page.
- Wizard tests rewritten for the create-only session flow (24 targeted tests pass;
  full `apps.app_entity` suite otherwise green).

---

## 2026-09-04 — Remove the executable coverage manifest

Removed `COVERAGE_MANIFEST` / `CoverageManifestTest`, the executable drift guard
that pinned one canonical test method per `(operation_type, action, side_effect)`
cell of the operation test-suite plan matrix. The guard only verified that each
declared `module:Class.method` path still resolved — the ~100 granular tests it
pointed at all remain and still run under `manage.py test`.

### Changed
- [`apps/app_operation/tests/base.py`](apps/app_operation/tests/base.py) — removed
  the `COVERAGE_MANIFEST` dict, `_path()`, `_test_method_exists()`,
  `CoverageManifestTest` and the now-unused `importlib` import (the Phase E block).
- Deleted the discovery shim
  `apps/app_operation/tests/test_coverage_manifest.py` (the manifest test is no
  longer discoverable by `test*.py`).
- Docs/specs: dropped the "Coverage manifest (executable branch registry)" rows
  from [`docs/operations/op_13_death.md`](docs/operations/op_13_death.md) and
  [`docs/operations/op_14_consumption.md`](docs/operations/op_14_consumption.md),
  and the "coverage manifest SE3/SE4" footnote in
  [`docs/operations/op_6_loan.md`](docs/operations/op_6_loan.md); reworded the
  now-dangling references in the `ai-plans/` summaries.
- [`ui_tests/manifest.py`](ui_tests/manifest.py) (its own self-contained mirrored
  manifest) is intentionally left unchanged.

---

## 2026-09-04 — Split `app_base` tests into a `tests` package

Converted the monolithic [`tests.py`](apps/app_base/tests.py) into an
`apps/app_base/tests/` package to match the rest of the project: the shared
fixtures moved to [`general.py`](apps/app_base/tests/general.py), and the test
classes were split into [`test_base_model.py`](apps/app_base/tests/test_base_model.py)
(BaseModel timestamps / soft-delete / post-save dispatch),
[`test_managers.py`](apps/app_base/tests/test_managers.py) (ActiveManager /
SafeQuerySet), [`test_mixins.py`](apps/app_base/tests/test_mixins.py)
(OfficerMixin / AmountCleanMixin), [`test_transaction_auto_creation.py`](apps/app_base/tests/test_transaction_auto_creation.py)
and [`test_seed_command.py`](apps/app_base/tests/test_seed_command.py).

### Changed
- `apps/app_base/tests.py` removed; `apps/app_base/tests/` package added with
  the same 39 test methods — pure structural refactor, no behavior change.

---

## 2026-09-04 — Remove the dormant `deletable` field

`BaseModel.deletable` was kept only for schema compatibility — deletion never
consulted it (every delete is a soft delete via `deleted_at`). The field, its
`save()` defaulting, and all references are now removed and the column is
dropped from every table.

### Changed
- [`BaseModel`](apps/app_base/models.py) — removed the `deletable` BooleanField
  and the new-row defaulting in `save()`.
- Removed `deletable=False` kwargs from test builders (operation view tests and
  [`general.py`](apps/app_inventory/tests/general.py)) and the
  `deletable`-field test in [`app_base/tests.py`](apps/app_base/tests.py).

### Added
- RemoveField migrations across the six apps (app_entity `0007`, app_inventory
  `0019`, app_operation `0012`, app_transaction `0005`, app_adjustment `0006`,
  app_animal `0003`). `app_animal/0003` depends on `app_inventory/0013`
  (MedicalRecord move copy) so the column is dropped only after that raw copy.

---

## 2026-09-04 — Add `manage.py clean` to purge soft-deleted rows

Soft delete accumulates tombstones forever; this is the admin/ops counterpart
that hard-deletes them. New `clean` management command
([`apps/app_base/management/commands/clean.py`](apps/app_base/management/commands/clean.py))
physically removes soft-deleted rows through Django's deletion collector (raw
SQL, so the soft-delete manager is bypassed) while respecting the `PROTECT`
schema: a tombstone still referenced by any other row is skipped until its
dependents are purged first (leaf-up, in rounds). Live rows are never touched.

### Added
- `manage.py clean` with options:
  - `--model APP.Model` — limit to one model (default: every model with
    `deleted_at`);
  - `--older-than DAYS` — only purge tombstones older than *DAYS* days;
  - `--dry-run` — report what would be purged without deleting.
- Purged rows are written to the audit channel (`<model>_purged` lines).
- Tests in [`test_clean_command.py`](apps/app_entity/tests/test_clean_command.py):
  leaf-up purge keeps live rows, dry-run removes nothing, `--older-than` skips
  recent tombstones, and a `--model`-scoped run leaves referenced tombstones in
  place.

---

## 2026-09-04 — Document that delete() is an admin-only action

`Model.delete()` (soft delete) is documented as an **admin-only** action. The
project UI must not render a view, form, or button that actually calls
`.delete()`; user-facing flows use deactivation, status transitions, or
reversal instead, and any real removal happens through Django admin so the
deletion guard and audit log apply.

### Added
- [`AGENTS.md`](AGENTS.md) — mandatory "Deletion policy" section.
- [`docs/guides/MODEL_CONVENTIONS.md`](docs/guides/MODEL_CONVENTIONS.md) —
  admin-only delete callout.

---

## 2026-09-04 — Soft-delete parent guard with configurable auto-delete

Deleting a parent that still has **live** dependents is now refused, mirroring
the DB `PROTECT` semantics under soft delete. [`BaseModel.delete()`](apps/app_base/models.py)
raises a `ValidationError` (`code="delete_blocked"`) listing, per dependent
type, what must be deleted (or reversed) first. Each model can declare reverse
relations in `_delete_auto_relations` that are **auto soft-deleted** with the
parent (excluded from the guard) — the mechanism for breaking circular
references so the guard cannot deadlock models that point at each other.
`_delete_guard_ignore_relations` lets a model fully ignore a relation.

### Changed
- [`BaseModel.delete()`](apps/app_base/models.py) — now guarded and
  transactional: refuse deletion while live non-auto dependents exist; auto
  soft-delete `_delete_auto_relations` dependents; re-entrancy safe so an
  auto-delete loop back to a record being deleted is a no-op.
- [`Entity`](apps/app_entity/models/__init__.py) — declares
  `_delete_auto_relations` for its owned light rows (`contacts`,
  `stakeholders`, `memberships`,
  `financial_categories_entities_relations`, `financial_periods`); financial
  history (products, operations, transactions) still blocks deletion.

### Added
- [`BaseModel.get_delete_blockers()`](apps/app_base/models.py) — reusable list
  of live dependent labels; [`BaseModel._auto_soft_delete_dependents()`](apps/app_base/models.py).
- [`test_soft_delete_guard.py`](apps/app_entity/tests/test_soft_delete_guard.py)
  — guard blocks + message, no partial deletes on failure, leaf-up delete,
  auto-delete of owned rows, and circular (mutually linked) entities deletable
  via auto relations.
- Documented the guard/configuration in
  [`docs/guides/MODEL_CONVENTIONS.md`](docs/guides/MODEL_CONVENTIONS.md).

---

## 2026-09-04 — Document mandatory `on_delete=PROTECT` model convention

Added a project instruction and guide so every new relationship declares
`on_delete=models.PROTECT` (no `CASCADE` / `SET_NULL` / `SET_DEFAULT`), matching
the PROTECT-only schema adopted earlier. Optionality stays expressed by
`null=True`, never by `SET_NULL`.

### Added
- [`AGENTS.md`](AGENTS.md) — mandatory "Model conventions" section stating that
  every new `ForeignKey` / `OneToOneField` / many-to-many `through` FK must use
  `on_delete=models.PROTECT`, with the soft-delete rationale and the
  review-required exception rule.
- [`docs/guides/MODEL_CONVENTIONS.md`](docs/guides/MODEL_CONVENTIONS.md) —
  guide covering why the project only soft-deletes, the rule with good/bad
  examples, `PROTECT` rationale, the leaf-up deletion workflow, exceptions, and
  a quick verification grep.
- Linked the new guide from
  [`docs/guides/README.md`](docs/guides/README.md).

---

## 2026-09-04 — Mark every foreign key PROTECT (no CASCADE / SET_NULL)

Deletion is always a soft delete — [`BaseModel.delete()`](apps/app_base/models.py)
stamps `deleted_at` and re-saves — so neither `on_delete=CASCADE` nor
`on_delete=SET_NULL` ever fires. Keeping those declarations was misleading
(Django admin treated cascade dependents as deletable and set-null relations as
"will be nulled") and left dependents silently referencing a hidden parent.
Every FK is now `PROTECT`: no relation is auto-removed or auto-nulled at the
schema level, all dependents are uniformly protected, and Django admin refuses
to delete a parent while any such row exists. This is the schema-side
precursor to the parent-with-children deletion guard.

### Changed
- `on_delete=CASCADE` → `PROTECT`: [`InvoiceItem.operation`](apps/app_inventory/models.py),
  [`Transaction.content_type`](apps/app_transaction/models.py),
  [`InvoiceItemAdjustmentLine.adjustment`](apps/app_adjustment/models.py),
  [`Stakeholder.parent` / `Stakeholder.target`](apps/app_entity/models/__init__.py),
  [`FinancialCategoriesEntitiesRelations.entity` / `.category`](apps/app_entity/models/category.py).
- `on_delete=SET_NULL` → `PROTECT` (nullability unchanged):
  [`InvoiceItemAdjustment.adjustment`](apps/app_adjustment/models.py),
  [`MedicalRecord.officer`](apps/app_animal/models.py),
  [`ProductTemplate.gives_birth_to`](apps/app_inventory/models.py),
  [`Product.mother`](apps/app_inventory/models.py),
  [`Transaction.reversal_of`](apps/app_transaction/models.py).

### Added
- Migrations: app_inventory `0017`, `0018`; app_transaction `0003`, `0004`;
  app_adjustment `0004`, `0005`; app_entity `0006`; app_animal `0002`.

---

## 2026-09-04 — Scope unique indexes to live (non-deleted) rows

Soft delete keeps rows forever, so a plain `unique=True` / `unique_together`
still considered a tombstone's value "taken" and re-creating the row raised
`IntegrityError`. Those constraints are now conditional (partial) unique indexes
over `deleted_at IS NULL`, so only live rows compete — an entity name,
product-template identity, product tag, financial-category name or
(entity, category) relation can be reused after a soft delete. The unique
idempotency key is intentionally **not** scoped: tombstones must keep those
values reserved so the same logical event can never be recorded twice.

### Changed
- [`Entity`](apps/app_entity/models/__init__.py) — `name` uniqueness moved from
  `unique=True` to the conditional `UniqueConstraint`
  `unique_entity_name_live` (`deleted_at IS NULL`).
- [`FinancialCategory`](apps/app_entity/models/category.py) and
  [`FinancialCategoriesEntitiesRelations`](apps/app_entity/models/category.py) —
  `unique=True` / `unique_together` replaced by the conditional
  `UniqueConstraint`s `unique_financial_category_name_live` and
  `unique_entity_category_relation_live`.
- [`ProductTemplate`](apps/app_inventory/models.py) — the six-field
  `unique_together` is now the conditional `UniqueConstraint`
  `unique_product_template_live`.
- [`Product`](apps/app_inventory/models.py) — the existing
  `unique_product_tag_per_entity` constraint now also requires
  `deleted_at IS NULL`, so a soft-deleted product no longer reserves its tag for
  the entity.

### Added
- Migrations
  [`apps/app_entity/migrations/0005_alter_financialcategoriesentitiesrelations_unique_together_and_more.py`](apps/app_entity/migrations/0005_alter_financialcategoriesentitiesrelations_unique_together_and_more.py)
  and
  [`apps/app_inventory/migrations/0016_remove_product_unique_product_tag_per_entity_and_more.py`](apps/app_inventory/migrations/0016_remove_product_unique_product_tag_per_entity_and_more.py).
- [`test_soft_delete_unique_reuse.py`](apps/app_entity/tests/test_soft_delete_unique_reuse.py) —
  entity name, financial-category name and (entity, category) relation reuse
  after soft delete; live duplicates are still rejected with a friendly
  `ValidationError`.
- Tag-reuse regression tests in
  [`test_product.py`](apps/app_inventory/tests/test_product.py).

---

## 2026-09-04 — Centralize delete logging in BaseModel

Removed the per-model `delete()` overrides that existed only to log an audit
line — they all forwarded to [`BaseModel.delete()`](apps/app_base/models.py),
which already performed the actual soft delete. Delete logging now lives in one
place.

### Changed
- [`BaseModel.delete()`](apps/app_base/models.py) — now emits the soft-delete
  logging itself: a `logger.warning` plus a flat, greppable `<model>_deleted`
  audit line carrying the model name, `pk`, `deleted_at` timestamp and the
  identifying fields the record exposes, so the context previously logged per
  model (operation type/amount/source/destination, contact type/value/entity,
  stakeholder parent/target/role, product template/quantity/status, ...) is
  preserved centrally.
- Removed the audit-only `delete()` overrides (they all forwarded to
  `BaseModel.delete()` and would otherwise double-log): `ContactInfo.delete()`,
  `Stakeholder.delete()`, `Operation.delete()`, `Adjustment.delete()` and
  `Product.delete()`. `Entity.delete()` is unchanged.

### Added
- `_DELETE_LOG_CONTEXT_FIELDS` and `_delete_log_context()` in
  `apps/app_base/models.py` — generic, field-driven context builder used by the
  central delete log.

---

## 2026-09-04 — Simplify deletion: every delete is now a soft delete

Removed the hard-delete machinery. Previously a record was physically removed
when `DEBUG` was on, or when the superuser-only `deletable` flag was set and the
acting user was a superuser; any other attempt either soft-deleted or raised.
Now `delete()` always soft-deletes — nothing is ever hard-deleted.

### Changed
- [`BaseModel.delete()`](apps/app_base/models.py) — always stamps `deleted_at`
  and re-saves. Removed the `DEBUG` bypass, the `deletable` gate (`RuntimeError`),
  the superuser hard-delete branch and the `crum` current-user dependency.
- Removed the `__setattr__` superuser guard for `deletable`. The `deletable`
  column is kept dormant for schema compatibility — deletion no longer consults
  it (dropping it needs a migration and is tracked separately).
- [`SafeQuerySet.delete()`](apps/app_base/managers.py) and
  [`OperationQuerySet.delete()`](apps/app_operation/models/managers.py) — iterate
  and soft-delete each row individually (no `DEBUG` bulk hard delete and no
  `NotImplementedError`), returning the standard `(count, {label: count})` tuple.
- [`EntityListView`](apps/app_entity/views/entity_list.py) — builds its queryset
  from `Entity.all_objects` so the "Deleted Only" and "All" deletion tabs can see
  soft-deleted entities.

### Added
- [`SoftDeleteTests`](apps/app_base/tests.py) in `apps/app_base/tests.py`:
  single and bulk `delete()` always soft-delete and are idempotent, and deleted
  rows stay hidden from `objects` yet remain reachable in `all_objects` and can
  be restored.

---

## 2026-09-04 — Complete ActiveManager soft-delete test coverage

### Added
- Expanded [`ActiveManagerTests`](apps/app_base/tests.py) in `apps/app_base/tests.py`
  to fully cover the soft-delete semantics of [`ActiveManager`](apps/app_base/managers.py):
  the default `objects` manager is an `ActiveManager` that excludes soft-deleted rows
  (`.all()`, `.count()`, `.filter()`, `.exists()`, and `.get()` raising
  `DoesNotExist`), while `all_objects` keeps soft-deleted rows reachable. Added
  manager-type assertions, restore (`deleted_at = None`) and multi-delete exclusion
  cases. Soft-deleted rows are produced through the real `delete()` path.

---

## 2026-09-03 — Docs reorganization (guides, operations, logging/testing)

Reorganized the Markdown docs site: pruned stale pages, moved the logging and
testing sections under the Guides area, and renumbered the per-operation specs.

### Removed
- `docs/operations/operations-comparison.md` — the consolidated cross-operation
  comparison. Dropped its per-operation "Cross-op reference" table rows, the
  operations `README.md` callout, the `_OPERATION_SPEC_TEMPLATE.md` template row,
  and the `docs/features/stock.md` cross-reference.
- `docs/guides/AUTHENTICATION.md` and `docs/guides/PROJECT_WALKTHROUGH.md`
  (their links were removed from `docs/guides/README.md`).

### Changed
- `docs/logging/` → `docs/guides/logging/` and `docs/testing/` →
  `docs/guides/testing/` (physical move). Repo-relative links inside the logging
  pages were bumped from `../../` to `../../../`.
- Renamed `docs/operations/op_*.md` to a sequential **1–15** series: internal
  transfer `op_5`, loan `op_6`, worker advance `op_7`, expense `op_8`, purchase
  `op_9`, sale `op_10`, correction `op_11`, birth `op_12`, death `op_13`,
  consumption `op_14`, capital valuation `op_15`. Updated every reference
  (`docs/operations/README.md`, `docs/features/stock.md`, cross-links inside the
  consumption spec).

### Updated
- [`docs/README.md`](docs/README.md) — Logging and Testing are now nested under
  the Guides category.
- [`docs/guides/README.md`](docs/guides/README.md) — links the Logging and
  Testing sub-sections.
- [`docs.py`](docs.py) — dropped Logging/Testing from the top navigation bar
  (now reachable under Guides).

---

## 2026-09-03 — Merge docs tooling into one docs.py pipeline

Consolidated the two standalone docs tools
([`debug_tools/build_pydoc_api.py`](debug_tools/build_pydoc_api.py) and
[`debug_tools/serve_docs.py`](debug_tools/serve_docs.py)) into a single pipeline
file [`debug_tools/docs.py`](debug_tools/docs.py) so the whole site (pydoc API
pages + rendered Markdown) is produced and served with one command.

### Added
- [`debug_tools/docs.py`](debug_tools/docs.py) — one entry point for the docs
  pipeline with subcommands:
  - `docs.py build [modules...]` — generate the pydoc API pages under
    `docs/api-docs/` (Django is bootstrapped lazily, only for this subcommand);
  - `docs.py serve [port]` — serve `docs/` as the styled site (default port
    8766);
  - `docs.py` (no args) — full pipeline: build, then serve on 8766.
- Kept the previous `build` behaviour of rendering a single named module, e.g.
  `docs.py build apps.app_entity.models`.

### Removed
- `debug_tools/build_pydoc_api.py` and `debug_tools/serve_docs.py` (folded into
  `debug_tools/docs.py`; run `.venv/bin/python debug_tools/docs.py` instead).

### Updated
- [`docs/README.md`](docs/README.md) — regenerate command now points to
  `debug_tools/docs.py build`.

### Verification
- Full `docs.py build` renders 129 module pages with 0 failures;
  `docs.py serve` returns HTTP 200 for the docs home, `README.md`, and
  `api-docs/`; the no-arg pipeline builds then serves successfully.

---

## 2026-09-03 — Consolidate logging & debugging docs into docs/logging

Merged the overlapping `docs/debugging/` and `docs/logging/` sections into one
canonical [`docs/logging/`](docs/logging/) section and removed stale docs that
pointed to the deleted custom debug machinery (`apps/app_base/debug.py`,
`queryset_logging.py`, `farm/middlewares_audit.py`, the `farm_debug` logger),
which had already been replaced with standard Python logging.

### Changed
- [`docs/logging/LOGGING_STANDARDS.md`](docs/logging/LOGGING_STANDARDS.md) —
  logging conventions; absorbed the per-area "Where logging lives" coverage
  (models/views/forms) previously in `docs/debugging/DEBUG_POINTS_INDEX.md`.
- [`docs/logging/LOGGING_IMPLEMENTATION_GUIDE.md`](docs/logging/LOGGING_IMPLEMENTATION_GUIDE.md) —
  how-to guide, no longer framed around the removed debug system.
- [`docs/logging/README.md`](docs/logging/README.md) — index for the merged section.

### Removed
- `docs/debugging/` (README, DEBUG_README, DEBUG_IMPLEMENTATION_SUMMARY,
  DEBUG_POINTS_INDEX, DEBUG_QUICK_REFERENCE).
- `docs/logging/COMPREHENSIVE_LOGGING_IMPLEMENTATION.md` — stale migration narrative.

### Updated
- [`docs/README.md`](docs/README.md) — dropped the Debugging category.
- [`debug_tools/serve_docs.py`](debug_tools/serve_docs.py) — removed the
  `Debugging` nav entry and now replies `404` for `.md` pages that no longer
  exist (previously the handler crashed that request thread).

---

## 2026-09-03 — docs/ as the documentation root (styled Markdown site)

Made `docs/` the single documentation root and added a server that renders the
Markdown pages as a styled, cross-linked site next to the pydoc API pages.

### Changed
- Generated pydoc API pages now live under `docs/api-docs/` (git-ignored);
  [`docs/README.md`](docs/README.md) links to them and the API index links back
  to the Markdown categories.
- Added [`debug_tools/serve_docs.py`](debug_tools/serve_docs.py): a stdlib HTTP
  server that renders every `docs/**/*.md` into styled HTML on the fly (shared
  CSS, top navigation bar, breadcrumbs, and an auto-generated "Related pages"
  sidebar), while serving `api-docs/` and other static files unchanged. It needs
  the pure-Python `markdown` package (`pip install markdown`).

### Usage
- Serve the docs root: `.venv/bin/python debug_tools/serve_docs.py` →
  http://localhost:8766/ (docs home) and http://localhost:8766/api-docs/ (API).

### Verification
- Home, guides, specs, operation specs, directory READMEs and `api-docs/` all
  return HTTP 200 as styled HTML; relative `.md` links resolve to rendered
  pages.

## 2026-09-03 — pydoc API-docs generator

Added a pydoc-based tool that renders the project's docstrings as static HTML
API reference pages.

### Added
- [`debug_tools/build_pydoc_api.py`](debug_tools/build_pydoc_api.py) — bootstraps
  Django (`DJANGO_SETTINGS_MODULE=farm.settings`, `django.setup()`), discovers
  every source module under `apps/` and `farm/` (excluding migrations, tests,
  `ui_tests`, `wsgi`/`asgi`/`settings`), writes one standalone pydoc HTML page
  per module into `docs/api-docs/` (flat dotted filenames so pydoc's
  cross-module links resolve), and builds a grouped `index.html`.
- `docs/` is the documentation root: [`docs/README.md`](docs/README.md) links to
  the generated API pages, and the API index links back to the raw Markdown
  categories. Serve `docs/` to browse everything on one origin:
  `python -m http.server 8766 --directory docs` → http://localhost:8766/ (docs
  home) and http://localhost:8766/api-docs/ (API reference).
- Output is intentionally git-ignored (`docs/api-docs/**`); regenerate with
  `.venv/bin/python debug_tools/build_pydoc_api.py`.

### Verification
- Full run renders **129 module pages with 0 failures**; pages carry the
  docstrings added across the models/mixins/proxies/views (verified in rendered
  HTML, e.g. `Entity.create`, `Entity.is_system`, `LoanOperation.clean_source`).
- `manage.py check` clean.

## 2026-09-03 — Method & remaining class docstrings

Added docstrings to the **business-logic methods** that lacked them, and the
remaining non-model **class** docstrings, across all apps. Documentation-only —
no behavior changes.

### Added
- Method docstrings on the core model classes and mixins:
  - [`app_base`](apps/app_base/models.py): `BaseModel` (`__setattr__`,
    `post_save`, `save`, `delete`), `ReversableModel` (`is_reversed`,
    `is_reversal`, validation guards, `_get_reverse_kwargs`, `reverse`).
  - [`app_base/mixins.py`](apps/app_base/mixins.py): `ImmutableMixin`,
    `AmountCleanMixin`, `OfficerMixin`, `AdjustableMixin`, the fund mixins,
    `HasRelatedTransactions`, `AutoTransactionMixin`, and the issuance /
    payment / repayment mixins.
  - [`app_base/managers.py`](apps/app_base/managers.py): `SafeQuerySet`
    methods and `ActiveManager.get_queryset`.
  - [`app_entity`](apps/app_entity/models/__init__.py): `Stakeholder.clean`,
    `Entity` type predicates, `create`, `payables_at` / `receivables_at`,
    `can_pay`, `save`; [`category.py`](apps/app_entity/models/category.py).
  - [`app_operation`](apps/app_operation/models/operation.py): reversal type
    lists, `get_related_entities`, `cast`, `clean`, `save`;
    [`period.py`](apps/app_operation/models/period.py);
    [`managers.py`](apps/app_operation/models/managers.py); every operation
    proxy in [`proxies/`](apps/app_operation/models/proxies/) (`clean_source`,
    `clean_destination`, fund/project/client/vendor properties, `clean`,
    reversal helpers).
  - [`app_inventory`](apps/app_inventory/models.py): `ProductTemplate`,
    `InvoiceItem`, `Product`, `InventoryMovementLine`, `ProductCapitalValuation`.
  - [`app_adjustment`](apps/app_adjustment/models.py): `AdjustmentType`
    classifiers, `Adjustment`, `InvoiceItemAdjustment`,
    `InvoiceItemAdjustmentLine`.
  - [`app_transaction`](apps/app_transaction/models.py): `owner`, reversal
    predicates, `clean`, `create`, `get_absolute_url`.
  - [`app_animal`](apps/app_animal/models.py): `MedicalRecord` choices.
- Remaining class docstrings:
  - The 7 `app_base` mixins (`BaseModelMixin`, `OfficerMixin`,
    `SourceFundMixin`, `TargetFundMixin`, `HasRelatedTransactions`,
    `LinkedIssuanceTransactionMixin`, `LinkedRePaymentTransactionMixin`) plus
    `SafeQuerySet`, `OperationQuerySet` / `OperationManager`.
  - The 4 view classes still missing one: `LoginView`, `OperationCreateView`,
    `BirthCreateView`, `DeathCreateView`.
  - The 8 `AppConfig` classes (each `apps.py`), the 11 choices/enum classes
    (`AdjustmentType`, `InvoiceItemAdjustmentType`, `OperationType`,
    `TransactionType`, `RecordType`, `HealthStatus`, `TrackingMode`, `Nature`,
    both `Gender`s, `Status`) and the 11 admin classes.
- Docstrings on **non-boilerplate view methods** across every app: entity
  (add/edit contact, stakeholder, person/project, category-relation views,
  detail/list), inventory (`StockDetailView`, `StockHistoryView`,
  `QuickConsumeView`, movement create/reverse/register views), operation
  (generic create, evaluation, purchase/sale wizards, adjustment recording,
  record payment/repayment, period close, operation reverse, list/detail/
  invoice-items/edit), transaction (payment list, payables/receivables,
  transaction detail/reverse), report (hub + statement views) and `app_base`
  (login/profile).
- Style kept consistent with the existing docstrings (concise English).

### Verification
- Re-ran the missing-docstring AST scanner: all class-level gaps in the four
  target areas are closed; remaining uncovered items are out-of-scope
  boilerplate/helpers (form `clean`/`__init__`, seed-command internals,
  module-level transaction-type helpers, validators, middleware, templatetag
  helpers).
- `manage.py check` clean; full app suite **1,471 tests OK**
  (`manage.py test apps --parallel=10 --keepdb`). The `ui_tests` browser suite
  was not run (repo convention).

## 2026-09-02 — Class docstrings for model classes

Added a class-level docstring to every Django model class that lacked one, so
each record type states what it represents and how it is used.

### Added
- Class docstrings for the core model classes across all apps:
  - [`app_base`](apps/app_base/models.py): `BaseModel`, `ReversableModel`.
  - [`app_entity`](apps/app_entity/models/__init__.py): `Entity`, `Stakeholder`,
    `ContactInfo`, `EntityType`, `StakeholderRole`; [`category.py`](apps/app_entity/models/category.py):
    `FinancialCategory`, `FinancialCategoriesEntitiesRelations`.
  - [`app_inventory`](apps/app_inventory/models.py): `ProductTemplate`,
    `InvoiceItem`, `Product`.
  - [`app_transaction`](apps/app_transaction/models.py): `Transaction`.
  - [`app_adjustment`](apps/app_adjustment/models.py): `Adjustment`.
  - [`app_operation`](apps/app_operation/models/proxies/): the 10 operation
    proxies without docstrings (`CashInjectionOperation`,
    `CashWithdrawalOperation`, `ExpenseOperation`, `InternalTransferOperation`,
    `LoanOperation`, `ProjectFundingOperation`, `ProjectRefundOperation`,
    `PurchaseOperation`, `SaleOperation`, `WorkerAdvanceOperation`).
- Docstrings describe each model's role, key fields and invariants (immutability,
  reversibility, stock/money effects), matching the surrounding code style.

### Verification
- Re-ran the model-class scanner: **every model class** in the project now has a
  class docstring; **0 syntax errors**.
- `manage.py check` clean.
- Full app test suite **1,445 tests OK**
  (`manage.py test apps --parallel=10 --keepdb`).

## 2026-09-02 — Module docstrings across the codebase

Added a purpose / overview docstring at the top of every project source module
that was missing one, so each module states what it provides.

### Added
- Module docstrings for **98 source modules** that previously had none, across
  the 8 apps (`app_adjustment`, `app_animal`, `app_base`, `app_entity`,
  `app_inventory`, `app_operation`, `app_report`, `app_transaction`) and the
  `farm/` project package — models, views, forms, urls, admin, apps.py, managers,
  mixins, templatetags, management commands, operation proxies and the
  `__init__.py` public namespaces.
- Purpose docstrings for **14 empty package `__init__.py` markers**.
- Kept style consistent with existing module docstrings (concise, English,
  `:class:`/`:mod:` cross-references). Excluded tests, migrations and
  `debug_tools`/`ui_tests` as planned.

### Verification
- Re-ran the module-docstring scanner: **0 source modules missing** a module
  docstring, **0 syntax errors**.
- `manage.py check` clean.
- Full app test suite **1,445 tests OK**
  (`manage.py test apps --parallel=10 --keepdb`). The `ui_tests` browser suite
  was not run (repo convention); its harness errors are unrelated to this change.
- Note: `apps/app_base/__init__.py` remains an empty package marker — its inode
  cannot be written on this filesystem (OS I/O error on every write path), so it
  was left as the conventional empty `__init__.py`.

## 2026-09-02 — Complete Arabic (ar) translation of the UI

Completed the Arabic localization of the whole application. The Arabic catalog
([`locale/ar/LC_MESSAGES/django.po`](locale/ar/LC_MESSAGES/django.po)) previously
covered only ~486 strings from an April snapshot; the current codebase carries
~1,216 translation-wrapped strings, so roughly **814 UI strings fell back to
English** when Arabic was selected.

### Changed
- Expanded the Arabic catalog from **486 → 1,216** message entries (labels,
  buttons, help text, validation messages, report headings, statuses, and
  screen text) across all apps and templates.
- Translated **6 plural counters** (`product(s)`, `movement(s)`, `item(s)`,
  `operation(s)`, `period(s)`, `transaction(s)`) with the full **6-form Arabic
  plural** set matching the catalog's `Plural-Forms` rule.
- Recompiled the binary catalog [`django.mo`](locale/ar/LC_MESSAGES/django.mo)
  from the updated `.po` (it had been stale since 2026-04-16).
- Pruned **84 stale entries** that no longer correspond to any string in the
  current source (removed features/old file paths).

### Verification
- All translation keys present in the source are now in the catalog and every
  entry has a non-empty Arabic translation.
- Confirmed end-to-end via Django: `Accounting System`, reports, forms and
  RTL screens resolve to Arabic, and plural counters inflect correctly
  (e.g. `7 عمليات`, `2 منتجان`, `12 حركةً`).
- `manage.py check` clean; full test suite **1,471 tests OK** (126 app_base /
  app_report / app_adjustment + 1,345 across the other apps).

## 2026-09-01 — Full UI test coverage for all operation actions

Completed the spec-driven browser UI suite for **every operation action's happy
path** ([`ai-plans/auto-ui-test-suite-plan.md`](ai-plans/auto-ui-test-suite-plan.md)),
checking all expected visible results per operation and honouring the dependency
chain between operations (e.g. a Sale requires an active project, received
purchase stock, and an active client). The full `ui_tests` suite now runs
**54 tests OK** (was 44).

### Added
- op_13 **Purchase** happy path ([`ui_tests/operations/test_purchase.py`](ui_tests/operations/test_purchase.py)):
  wizard create → receive items → pay → reverse; asserts flash, detail totals,
  movement status, fund movement and settlement.
- op_14 **Sale** happy path ([`ui_tests/operations/test_sale.py`](ui_tests/operations/test_sale.py)):
  dependency-aware (active project + received purchase stock + active funded
  client), wizard create → dispatch goods → collect → reverse (movement undone first).
- op_17 **Birth** happy path ([`ui_tests/operations/test_birth.py`](ui_tests/operations/test_birth.py)):
  mother → newborn; auto inbound movement, ACTIVE newborn, no transactions, reverse
  removes the newborn.
- op_18 **Death** happy path ([`ui_tests/operations/test_death.py`](ui_tests/operations/test_death.py)):
  write-off an existing animal; DEAD status, reverse restores ACTIVE.
- op_19 **Consumption** happy path ([`ui_tests/operations/test_consumption.py`](ui_tests/operations/test_consumption.py)):
  consume a FEED batch; CONSUMED status, reverse restores ACTIVE.
- Wizard/frame helpers in [`ui_tests/base.py`](ui_tests/base.py): `click_wizard_next`,
  `goto_query`, `fill_date`, `reverse_transaction`; `make_product_template` now
  derives the tracking mode from the nature in [`ui_tests/operations/helpers.py`](ui_tests/operations/helpers.py);
  new clauses registered in [`ui_tests/manifest.py`](ui_tests/manifest.py).

### Fixed
- [`invoice_formset.html`](apps/app_operation/templates/app_operation/snippets/create-form/invoice_formset.html)
  now renders the select-mode `selected_product` picker for **Death/Consumption**
  create forms — previously only the create-mode `product_template` was rendered,
  leaving those forms unusable through the browser (spec §8 contract restored).
- Pre-existing UI tests: Capital Gain/Loss evaluation now fills the required `date`
  field; Expense happy path reverses the payment transaction before the operation
  reversal (matching the VR3 reversal guard).

---

## 2026-09-01 — Fresh refactor scan: logging standardization & error-details dedup

A behavior-preserving cleanup following the fresh refactor scan
([`ai-plans/fresh-refactor-scan-plan.md`](ai-plans/fresh-refactor-scan-plan.md)). Verified
with `manage.py check`, `makemigrations --check` (no changes), and the full non-UI suite
(**1469 tests OK**).

### Refactor
- Replaced all **12 raw `traceback.print_exc()`** calls with structured
  `logger.exception(...)` in [`apps/app_inventory/views.py`](apps/app_inventory/views.py),
  [`apps/app_base/reversal.py`](apps/app_base/reversal.py), and the operation
  `record_transaction` / `evaluation` / `base` views; removed now-unused `traceback`
  imports.
- Added [`build_error_details()`](apps/app_base/logging_utils.py) to
  [`apps/app_base/logging_utils.py`](apps/app_base/logging_utils.py) and refactored the
  25+ duplicated `error_details = {...}` exception blocks (entity views, wizard steps,
  category views, reversal, operation views) to delegate to it — log/audit/message
  strings preserved byte-for-byte.

---

## 2026-09-01 — Code quality & refactoring sweep (Phase 2)

A large, mostly behavior-preserving refactoring pass across views, models, and shared
helpers. See [`ai-plans/IMPLEMENTED_PLANS_SUMMARY.md`](ai-plans/IMPLEMENTED_PLANS_SUMMARY.md)
for the consolidated plan record and [`ai-plans/long-function-refactor-phase-2-plan.md`](ai-plans/long-function-refactor-phase-2-plan.md).

### Refactor
- Split long functions/methods project-wide per the phase-2 plan (phases 2–10),
  including the earlier Phase 3 pass.
- Converted function-based views to **class-based views** ([`877c536`]).
- Split [`AddStakeholderView`] into focused methods and added tests ([`0db29c4`]).
- Extracted shared helpers across apps and split long functions ([`6b0e99b`]).
- Moved POST/business logic into models, forms, and shared helpers
  ([`01ad71c`]); decoupled `EvaluationCreateView` from `OperationCreateView`
  ([`8c8baa0`]).
- Consolidated the stock-detail direction queryset into
  `stock.portfolio_direction_q` ([`de14d77`]).
- Removed `Entity.fund` property and its `hasattr` sentinel ([`9d508ef`]).
- Replaced the custom debug/audit machinery with **standard Python logging**
  ([`bc0399e`]).
- Dead-code removal: Phase 0 cleanup ([`7f81264`]), a second cleanup sweep
  ([`c031b11`]), and removal of the dead `initial_period` signal ([`b166923`]).

### Fixed
- Implemented the **VA3 guard**: an item's quantity can no longer shrink below the
  quantity already moved ([`a02eee3`]).

### Docs
- Consolidated implemented `ai-plans/*.md` into
  [`ai-plans/IMPLEMENTED_PLANS_SUMMARY.md`](ai-plans/IMPLEMENTED_PLANS_SUMMARY.md)
  and removed the per-plan files that were fully implemented.
- Fixed broken markdown links across the `docs/` tree ([`921dd01`]).
- Merged the Capital Gain & Capital Loss specs into a single
  `capital_valuation_operation.md` ([`733ba9f`]).
- Added this `CHANGES.md`.

### Other
- Added a [`VERSION`](VERSION) file at the repo root, establishing a semantic
  versioning baseline (`1.0.0`) for the project.

---
 
 ## 2026-08-15 — Reports, operation mixins, proxy merges, UI test suite

### Added
- **Financial statements UI** in a new `apps/app_report` app: hub + Income Statement,
  Balance Sheet, Cash Flow, and Statement of Changes in Equity, period-scoped with
  drill-down links and print-friendly layouts ([`60a1326`]).
- Selenium UI test suite phases: Phase 0 harness + op_1 clauses ([`8fc54c5`]),
  Phase 1 one-shot operations op_2–op_7 / op_15 ([`ad6544a`]), and payable-op /
  global clause tests (loan, worker advance, auth, entities, crosscutting)
  ([`64bf66e`]).

### Refactor
- Extracted inventory behavior from `Operation` into mixins
  (`InventoryOperationMixin`, `StockEventMixin`) ([`ba9c565`]).
- Abstracted one-shot operation config via `OneShotTransactionMixin` ([`0b01b9e`]).
- Merged `CapitalGainOperation` + `CapitalLossOperation` into a single
  `CapitalValuationOperation` proxy ([`982f289`]).
- Merged `CorrectionCreditOperation` + `CorrectionDebitOperation` into a single
  `CorrectionOperation` proxy ([`6fcf4d7`]).

### Other
- "Fast testing" settings optimization for `manage.py test` ([`5173aee`]).

---

## 2026-08-14 — Spec test-pinning & stock-event cleanup

### Fixed
- Strip accounting/transaction mixins from the 5 stock-event operations (Birth, Death,
  Consumption, Capital Gain, Capital Loss) so they no longer create `Transaction`
  rows ([`1d7ff7e`]).
- Replaced the `InvoiceItem` M2M value link for Capital Gain/Loss with a dedicated
  `ProductCapitalValuation` table ([`1bfc930`]).

### Tests
- Closed `op_19` consumption spec coverage gaps ([`2e0ecb5`]).
- Added comprehensive Death (`op_18`) coverage ([`7dc3ba3`]).
- Closed Birth (`op_17`) spec coverage gaps ([`df00a23`]).
- Closed operations spec test-coverage gaps (VR4 guard, SR9/SR10) ([`91f55d6`]).

### Docs
- Pinned every operation contract branch to its test ([`887991a`]).
- Fully rewrote the 5 stock-event operation specs to remove stale transaction/COGS
  references ([`b04d93d`]); synced `stock.md` with the stock-event specs ([`de28a65`]).
- Added the financial reports feature spec ([`514f185`]) and stripped Arabic from it,
  adding model-level calculation recipes ([`34c71c7`]).

---

## 2026-08-13 — Movement-based inventory, sale rework, spec V2 contracts

### Added / Changed
- **Dropped `ProductLedgerEntry`**; stock is now computed from movement lines via
  [`apps/app_inventory/stock.py`](apps/app_inventory/stock.py) ([`10598ac`]).
- **Sale from existing stock**: the sale wizard is now the only sale path, selecting
  the seller's existing products (`f778a77`).
- Moved `MedicalRecord` into a new `apps/app_animal` app ([`f0ad0cf`]).
- Birth double-count fix: made virtual value ops (Birth/Death/Capital Gain/Loss)
  **non-cash** and switched `FinancialPeriod.end_assets` to movement-based inventory
  value ([`c40fc05`]).
- Removed **Profit Distribution & Loss Coverage** operations ([`53901b4`]).
- Allowed purchase operation reversal once payments and movements are reversed
  ([`194ea5b`]).
- External and virtual funds may now pay without balance checks ([`13c5c0e`]).
- Restricted the Birth mother picker to ACTIVE female/mixed animals (VC17)
  ([`9f8e2f2`]).
- Added a red-outlined **Reverse** link beside Print on the operation detail page
  ([`2f72bc0`]).
- Removed dead code ([`a311d83`]).
- Widened nearly every operation spec to the **v2 contract format** (cash injection
  [`5bc51fc`], withdrawal [`2963b36`], funding/refund [`e94e05f`], transfer [`5af8fc1`],
  loan [`055e9cd`], expense [`8787ac6`], purchase [`5fa98ed`], sale [`eef9ec8`],
  correction [`3b6740c`], birth/death [`58362a1`], consumption [`88f1acf`],
  capital gain/loss [`0fbf349`]).

### Tests
- Added focused Internal Transfer tests for SC3, SR9, SR10 ([`3fe2951`]).
- Pinned reversal-op-owns-no-txs (CC35/CD35) for correction ([`9dc53d2`]).
- Closed stock spec coverage gaps in `app_inventory` ([`4c793e0`]).

---

## 2026-08-12 — UI rework, loan fixes, test overhaul

### Added / Changed
- Reworked **stock detail** with per-product physically-present cards, and added a new
  **stock history** page ([`ea403fb`]).
- Marked reversed-born products as removed and enforced product ownership
  ([`09f49eb`]).
- Blocked loan repayment without disbursement and capped repayments by the paid sum
  ([`0fd6150`]).
- Excluded reversal mirrors from payables and receivables ([`d710c41`]).
- Showed source-fund balance on operation and transaction create pages ([`3bbd37d`]).
- Showed payables, receivables, and stock value on the entity detail page ([`c7f587a`]).
- Reworked the operations list with a balance card, statuses, and progress bars
  ([`3498e2f`]).
- Improved operation-detail navigation and settlement actions ([`a334b59`]).
- Restored the repaid state after a repayment transaction is reversed ([`fdb8cfb`]).
- Added an entity transactions list view for balance tracking ([`a3d841a`]).

### Tests
- Overhauled the operation test suite with granular one-side-effect-per-test coverage
  ([`a628b08`]).
- Added the internal entity stock-transfer plan and updated the TODO tracker
  ([`a3b799b`]).

---

## 2026-08-10/08-11 — Animal tracking, seeding, integrity

### Added
- Animal tracking fields on `ProductTemplate` / `Product` and a new `MedicalRecord`
  model ([`e0c4605`], [`519f100`], [`eb7df55`]).
- Captured newborn gender, birth date, and mother in birth operations ([`48a2aa9`]).
- Seeded animal templates by **species × stage × gender** ([`869790b`]).
- Individual-animal tracking, closed-period guards, and inventory-integrity fixes
  ([`4b74127`]).
- Improved login redirect behavior ([`f67c10f`]).

---

## 2026-05 — Financial periods, logging, UI test expansion

### Added / Changed
- Added financial-period views and balance-calculation methods ([`666df06`]).
- Refactored `FinancialPeriod` lifecycle to automatic reconciliation ([`f3bd8db`]) and
  converted `FinancialPeriod.amount` from a stored field to a calculated property
  ([`b2cf717`]).
- Blocked manual period creation for active entities with existing periods
  ([`65b36df`]) and switched the period-creation guard to a redirect-with-messages
  ([`024aed6`]).
- Added a comprehensive navigation row across all views ([`035044d`]).
- Applied comprehensive logging across the entire project ([`77199e1`], [`8aef009`]),
  with test-mode guards on `DebugContext` ([`2494a4a`]).
- `InvoiceItem` now respects adjustments ([`3b44432`]); flattened products on deferred
  movement ([`ccf53cb`]).
- Added paid/remaining amount columns to the operation list ([`39afd97`]).

### Tests
- Expanded the UI test suite to cover 10 key views across all modules ([`80ebec0`]) and
  fixed viewport/authentication handling ([`66efaf5`]).
- Split test files into one file per test class (29 → 135 files) ([`e7a71b6`]).

---

## 2026-04 — Core implementation & early tests

### Added
- Project setup and the personal-operation model ([`3bdb63e`]).
- Expense & financial categories ([`dde5cd8`]).
- Adjustments implementation ([`df0d558`]).
- Fixed the post-save task dispatch key matching in `BaseModel` / `Operation`
  ([`70fce21`]) and the purchase wizard ([`fabedda`]).

### Tests
- Cash-injection test ([`0652051`]), AI tests ([`c79548d`]), test suites for
  Capital Loss / Internal Transfer / Loan and spec-file renames ([`3545b93`]),
  financial-period tests ([`76c7e57`]), and distribution-plan tests ([`39277a9`]).

---

## 2026-03 — Project inception

- Initial Entity model & views (person, project, category, fund) ([`c23fd37`]).
- Moved "get related entities" logic to the operation proxy ([`bc7631f`]).
- Fixes to adjustments ([`07b132e`]).
- Expense & categories groundwork ([`dde5cd8`]).



## How this file is maintained

- Grouped by date (most recent first), then by type (Added / Changed / Fixed / Tests /
  Docs / Refactor / Other).
- References the relevant git commit(s) and related planning documents in
  [`ai-plans/`](ai-plans/).
- For feature-level behavior, see the specs in [`docs/specs/`](docs/specs/) and the
  consolidated [`ai-plans/IMPLEMENTED_PLANS_SUMMARY.md`](ai-plans/IMPLEMENTED_PLANS_SUMMARY.md).
