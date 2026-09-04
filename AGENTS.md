# AGENT INSTRUCTIONS FOR THE FARM PROJECT

## Project overview
- This repository is a Django project named `farm`.
- The main Django apps live under `apps/`, including `app_inventory`, `app_operation`, `app_transaction`, `app_adjustment`, `app_entity`, and `app_base`.
- The project entry points are `manage.py`, `farm/settings.py`, and `pytest.ini`.

## Working conventions
- Prefer small, targeted changes that match the surrounding code style.
- Follow the existing Django pattern: models for data logic, forms/views for request handling, templates for presentation.
- Keep changes consistent with the current app structure and naming conventions.
- Avoid editing generated or environment-specific artifacts such as coverage reports, `db.sqlite3`, or virtualenv contents unless the task explicitly requires it.
- Preserve existing behavior unless the task is clearly a bug fix or feature change.

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

## Testing and verification
- Use Django's built-in test runner: `manage.py test`. Settings auto-optimize
  for speed (in-memory sqlite for serial runs, RAM-backed `/dev/shm` DB for
  parallel runs, fast MD5 password hashing, reduced logging).
- Fastest commands:
  - `manage.py test --parallel=10 --keepdb` (reuse the test DB)
  - `manage.py test --parallel=10` (run once after schema changes, then `--keepdb`)
- Prefer running targeted tests for the area you changed before running the full suite.
- Common verification commands:
  - `manage.py test <app.tests.module>`
  - `manage.py check`
- If a change affects models or business logic, add or update tests where appropriate.
- Capture full test output into a temporary file under `tmp/` (repo root) for
  checking errors, then delete the temp file when done.

## Repo-specific notes
- The project depends on Django and related packages listed in `requirements.txt`.
- If a virtual environment exists at `.venv`, prefer using it for Python commands.
- Be mindful of localization and existing templates when changing UI strings or workflows.
- When investigating issues, inspect the relevant app and its tests before changing code.
