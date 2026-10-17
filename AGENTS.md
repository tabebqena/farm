# AGENT INSTRUCTIONS FOR THE FARM PROJECT

## Project overview
- Django 6 project `farm`: a financial management platform for a livestock farm
  business. Domain flow: **Entities** (people/projects/vendors/clients) run
  **Operations** (business events) that generate **Transactions** (ledger
  entries) against **Funds** (each entity's wallet), plus invoices, adjustments,
  inventory, and animals.
- All Django apps live under the `apps/` package and are registered as
  `apps.app_*`: `app_base`, `app_entity`, `app_transaction`, `app_operation`,
  `app_adjustment`, `app_inventory`, `app_animal`, `app_report`.
- Entry points: `manage.py`, `farm/settings.py`, `farm/urls.py`. URL prefixes
  (all i18n-wrapped): `/entities/`, `/transactions/`, `/inventory/`,
  `/reports/`, `/auth/`, `/admin/`; root redirects to `entity_list`.
- Release sources of truth: `VERSION` (semver) and `CHANGES.md`. Repo convention
  is to update both after an edit.
- Non-obvious layout:
  - `app_base` is the cross-cutting app: `BaseModel`/`ReversableModel`, managers,
    mixins, reversal, logging, navigation/context processors.
  - Operation "types" are **proxy models** in
    `apps/app_operation/models/proxies/*.py` (e.g. `op_loan`, `op_sale`,
    `op_purchase`), all subclassing `Operation` in
    `apps/app_operation/models/operation.py`; the type enum lives in
    `operation_type.py`. `app_operation` uses a `models/` **package** (not a
    module); most other apps use `models.py`.
  - Financial periods live in `apps/app_operation/models/period.py`.

## Model conventions (mandatory)
- Every new relationship — `models.ForeignKey`, `models.OneToOneField`, and the
  `models.ForeignKey` fields of any many-to-many `through` model — MUST declare
  `on_delete=models.PROTECT`.
- Do NOT use `on_delete=models.CASCADE`, `SET_NULL`, or `SET_DEFAULT` in new
  code. `null=True` stays allowed for optional relationships: optionality is
  expressed by nullability, never by `SET_NULL`.
- Why: the project deletes exclusively via soft delete —
  [`BaseModel.delete()`](apps/app_base/models.py) stamps `deleted_at` and
  re-saves, so DB-level `CASCADE`/`SET_NULL` never fire. `PROTECT` keeps every
  dependent row visible as a protected object: a parent cannot be deleted while
  dependents exist, and dependents must be deleted (or reversed) first, which
  preserves the audit trail.
- Any deviation requires discussion and an explicit justification before it is
  merged (legacy/unchanged schema fields are fine as-is; this rule governs new
  code).
- Details and rationale: [`docs/guides/MODEL_CONVENTIONS.md`](docs/guides/MODEL_CONVENTIONS.md).

## Deletion policy (mandatory)
- [`delete()`](apps/app_base/models.py) (soft delete via `deleted_at`) is an
  **admin-only** action. Only Django admin (a staff superuser) may invoke it.
- The project UI must NOT display a view, form, or button that actually calls
  `.delete()` / soft-deletes a record. User-facing flows use domain actions
  instead: deactivation (`active` / `is_active`), status transitions, or
  reversal — never `delete()`.
- New views/forms/templates must not add a delete endpoint or "delete" control
  that maps to `Model.delete()`. If a row genuinely must be removed, it is done
  through the Django admin so the soft-delete guard (PROTECT semantics) and the
  audit log apply.

## Persistence quirks (will bite you)
- Every model inherits `BaseModel`, whose `save()` runs `full_clean()` on
  **every** save (including soft delete). Persist with individual `.save()`;
  construct objects with valid data.
- `SafeQuerySet` ([`apps/app_base/managers.py`](apps/app_base/managers.py))
  blocks queryset `.update()`, `.bulk_create()`, and (outside `DEBUG`)
  `.bulk_update()`; queryset `.delete()` soft-deletes rows one at a time. Do not
  write bulk operations that bypass validation.
- `objects` hides soft-deleted rows; `all_objects` sees everything.

## Testing and verification
- Tests run through Django's runner, **not pytest** (`pytest.ini` exists but is
  not the workflow). Prefer the project venv: `.venv/bin/python manage.py ...`.
- Settings auto-optimize under `manage.py test`: in-memory sqlite for serial
  runs, RAM-backed `/dev/shm` DB for parallel runs, fast MD5 password hashing,
  reduced logging.
- Fastest commands:
  - `.venv/bin/python manage.py test <target> --parallel=10 --keepdb` (reuse test DB)
  - `.venv/bin/python manage.py test <target> --parallel=10` (run once after schema changes, then `--keepdb`)
- Focused checks: `.venv/bin/python manage.py test apps.app_operation.tests.<module>`
  and `.venv/bin/python manage.py check`.
- Coverage is configured in `.coveragerc` (`fail_under = 100`); HTML report goes
  to `htmlcov/`.
- UI tests (`ui_tests/`, Selenium + `LiveServerTestCase`) are a separate,
  **serial-only** suite: `python3 manage.py test ui_tests --keepdb` (no
  `--parallel`). Do not run them unless asked. Env: `FARM_UI_HEADFUL=1`,
  `FARM_UI_BROWSER=firefox`. Failures save screenshot + HTML to
  `test_screenshots/`.
- Capture full test output into a temporary file under `tmp/` (repo root), then
  delete the file (keep the `tmp/` directory).

## Working conventions
- Prefer small, targeted changes that match the surrounding code style.
- Keep planning/design documents in `ai-plans/`; after executing a plan, append
  what was implemented to that plan file.
- When asked to change behavior, search the specs under `docs/` first; if the
  behavior is intended, surface the spec and an impact analysis before editing.
- Avoid editing generated or environment-specific artifacts: `db.sqlite3`,
  `.coverage`, `htmlcov/`, `logs/`, `test_screenshots/`, `docs/api-docs/`,
  `.venv/`, and `*.pyc`.
- Regenerate/serve the docs site with `.venv/bin/python docs.py build`
  (or `serve`, default port 8766); index is `docs/README.md`.
