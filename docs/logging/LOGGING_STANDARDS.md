# Logging Standards - Farm Project

## Overview

The project uses **standard Python logging**. The previous custom
`apps.app_base.debug` machinery (`DebugContext`, `debug_view`/`debug_transaction`
decorators, JSON audit envelopes, per-request `AuditTrailMiddleware`, and the
`queryset_logging` module) was removed on 2026-09-01 because it was overengineered
and noisy. In its place there are two loggers configured via `LOGGING` in
`farm/settings.py`:

| Logger | Purpose | Handlers | Default level |
| --- | --- | --- | --- |
| `farm` | One project-wide logger for all application logging | `console`, `debug_file` (`logs/debug.log`) | `INFO` |
| `farm_audit` | Compliance-only audit channel | `audit_file` (`logs/audit.log`) | `INFO` |

A dedicated `error_file` (`logs/errors.log`, `ERROR`) is attached to the root
logger. All handlers are rotating (10MB, with backups).

## How to Use

### Regular logging

```python
from apps.app_base.logging_utils import logger

logger.debug(f"Processing user {user.pk}")      # silent unless level is DEBUG
logger.info("Significant event")
logger.warning("Suspicious but recoverable condition")
logger.error("Something failed")
```

- The shared `farm` logger is used everywhere — there is **no** per-module
  `logging.getLogger(__name__)`.
- Verbose per-step "success" / "section" noise was dropped or demoted to
  `logger.debug(...)`.
- To trace at runtime, raise the `farm` logger level to `DEBUG` in
  `farm/settings.py` — no code changes needed.

### Audit (compliance) logging

```python
from apps.app_base.logging_utils import audit_logger

audit_logger.info(f"transaction_reversed | Transaction:{tx.pk} | "
                  f"user={officer} | reversal_pk={reversal.pk}")
```

Use `audit_logger` **only** for compliance events: create/update/delete of key
records (entities, operations, adjustments, products, stakeholders, contacts),
reversals, and financial period close. Audit lines are flat and greppable:

```
transaction_reversed | Transaction:42 | user=officer | reversal_pk=57 | reason=...
```

## Log Levels

| Level | Usage |
| --- | --- |
| `DEBUG` | Detailed execution flow (silent by default) |
| `INFO` | Significant application events |
| `WARNING` | Suspicious but recoverable conditions |
| `ERROR` | Failures requiring attention |
| `CRITICAL` | System failures |

## What Should Be Audited

- Financial transactions (create, reverse, adjust)
- Operation create/update/delete and reversals
- Entity / stakeholder / contact create/update/delete
- Adjustment create/delete and reversals
- Product create/update/delete
- Financial period close
- Failed reversals and creation attempts

## What Should Be Logged at DEBUG

- Form validation flow
- Query/fetch counts
- View setup and processing steps
- Internal computation details

## Deleted / superseded components

- `apps/app_base/debug.py` (DebugContext + decorators) — deleted
- `apps/app_base/queryset_logging.py` (LoggingQuerySet / LoggingManager) — deleted
- `farm/middlewares_audit.py` (AuditTrailMiddleware) — deleted
- `LoggingFormMixin` — kept, but rewritten on standard logging
- `farm_debug` logger — removed; use the shared `farm` logger
