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
