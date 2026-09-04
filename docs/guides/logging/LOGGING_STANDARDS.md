# Logging Standards - Farm Project

## Overview

The project uses **standard Python logging** with two channels configured via
`LOGGING` in [`farm/settings.py`](../../../farm/settings.py):

| Logger | Purpose | Handlers | Default level |
| --- | --- | --- | --- |
| `farm` | One project-wide logger for all application logging | `console`, `debug_file` (`logs/debug.log`) | `INFO` |
| `farm_audit` | Compliance-only audit channel | `audit_file` (`logs/audit.log`) | `INFO` |

Both loggers are exposed from
[`apps/app_base/logging_utils.py`](../../../apps/app_base/logging_utils.py):
`from apps.app_base.logging_utils import logger, audit_logger`.

- The `farm` logger defaults to `INFO`, so `logger.debug(...)` calls are silent
  unless tracing is enabled.
- The root logger also captures `ERROR`+ to `error_file` (`logs/errors.log`).
- `django.db.backends` SQL is routed to `debug_file` at `INFO`.
- All handlers are rotating (10MB, with backups).

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
- Verbose per-step "success" / "section" noise is dropped or demoted to
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

## Where Logging Lives

There are no custom decorators or context managers — log the meaningful steps
explicitly at `debug`, and emit `audit_logger` lines for compliance events.

### Models

| File | Logging |
| --- | --- |
| [`apps/app_base/models.py`](../../../apps/app_base/models.py) | `BaseModel.delete()` — central soft-delete logging: emits a `logger.warning` plus the `<model>_deleted` audit line for every model (per-model `delete()` overrides removed) |
| [`apps/app_transaction/models.py`](../../../apps/app_transaction/models.py) | `clean()`/`create()` at debug; `reverse()` audits (`transaction_start`/`transaction_reversed`/`transaction_reversal_failed`) |
| [`apps/app_adjustment/models.py`](../../../apps/app_adjustment/models.py) | `clean()`/`save()`/`finalize()`/`reverse()` at debug + `adjustment_*` audits (delete audit via `BaseModel.delete()`) |
| [`apps/app_inventory/models.py`](../../../apps/app_inventory/models.py) | `Product.clean()`/`save()` at debug + `product_*` audits (delete audit via `BaseModel.delete()`) |
| [`apps/app_operation/models/operation.py`](../../../apps/app_operation/models/operation.py) | `clean()`/`save()`/`reverse()` at debug + `operation_*` audits (delete audit via `BaseModel.delete()`) |
| [`apps/app_entity/models/__init__.py`](../../../apps/app_entity/models/__init__.py) | entity/stakeholder/contact save at debug + `entity_*`/`stakeholder_*`/`contact_info_*` audits (delete audit via `BaseModel.delete()`) |

### Views

| Area | Logging |
| --- | --- |
| `apps/app_entity/views/*` | entity/contact/stakeholder/category views: fetch + processing at debug, `*_created`/`*_updated`/`*_failed` audits |
| `apps/app_operation/views/*` | operation detail/list/edit/period/reverse/record views: fetch + processing at debug, reversal/creation audits |
| `apps/app_operation/views/create_operation/*` | create views (base/birth/death/evaluation/wizards): setup + creation at debug, `operation_created`/`operation_creation_failed` audits |
| [`apps/app_transaction/views.py`](../../../apps/app_transaction/views.py) | transaction list/detail/reverse: fetch + processing at debug, reversal audits |
| [`apps/app_report/views.py`](../../../apps/app_report/views.py) | report scope resolution at debug |

### Forms

All forms inherit [`apps/app_base/form_logging.py`](../../../apps/app_base/form_logging.py)
(`LoggingFormMixin`):

- `clean()` logs at debug; validation errors log a warning.
- `save(commit=True)` emits a `form_create`/`form_update` audit line.

## History

The project previously used a custom debug/audit layer
(`apps/app_base/debug.py` `DebugContext` + decorators, `queryset_logging`,
`AuditTrailMiddleware`, and a `farm_debug` logger). That layer was replaced with
the two standard loggers above on 2026-09-01 (see
`ai-plans/replace-debug-with-standard-logging-plan.md`). Logging is now plain
`logging` — no custom decorators or context managers are used.
