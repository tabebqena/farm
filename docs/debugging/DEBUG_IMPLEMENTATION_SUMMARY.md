# Debug Implementation Summary

## 2026-09-01 — Migrated to standard Python logging

The previous custom debug/audit machinery was replaced with idiomatic
`logging` to reduce noise and overengineering.

### Removed

- `apps/app_base/debug.py`
  - `DebugContext` (section/log/success/warn/error/audit/transaction_*)
  - Decorators: `debug_function`, `debug_model_save`, `debug_view`,
    `debug_signal`, `debug_db_operation`, `debug_transaction`
  - Test-mode gating and the duplicate audit file handler
- `apps/app_base/queryset_logging.py` (`LoggingQuerySet` / `LoggingManager`)
- `farm/middlewares_audit.py` (`AuditTrailMiddleware`) and its `MIDDLEWARE` entry
- `farm_debug` logger from `LOGGING`

### Added / kept

- `apps/app_base/logging_utils.py`
  ```python
  logger = logging.getLogger("farm")          # one project-wide logger
  audit_logger = logging.getLogger("farm_audit")  # compliance-only channel
  ```
- `farm/settings.py` `LOGGING`:
  - `farm` logger → `console` + `debug_file`, level `INFO`
  - `farm_audit` logger → `audit_file`, level `INFO`
  - `django.db.backends` → `INFO`
  - test mode silences both `farm` and `farm_audit`
- `apps/app_base/form_logging.py` (`LoggingFormMixin`) rewritten on standard
  logging (still inherited by all forms)

### Migration mapping

| Old | New |
| --- | --- |
| `DebugContext.log(...)` | `logger.debug(f"...")` |
| `DebugContext.success(...)` | dropped or `logger.debug(...)` |
| `DebugContext.warn(...)` | `logger.warning(...)` |
| `DebugContext.error(...)` | `logger.error(...)` |
| `with DebugContext.section(...)` | removed; body de-indented, meaningful steps logged |
| `DebugContext.audit(...)` | `audit_logger.info(f"action | Type:id | ...")` |
| `transaction_start/commit/rollback` | `audit_logger.info/error(...)` |
| `@debug_view` / `@method_decorator(debug_view)` | removed |
| `@debug_transaction` | removed |
| `logger = logging.getLogger(__name__)` | `from apps.app_base.logging_utils import logger` |

### Verification

- `manage.py check` → no issues
- `manage.py test apps --parallel=10 --keepdb` → 1460 tests, OK
