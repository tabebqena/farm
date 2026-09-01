# Debug Logging System

## Overview

The Farm project uses **standard Python logging**. The custom debug system
(`DebugContext`, `debug_view`/`debug_function`/`debug_signal` decorators,
`queryset_logging`, `AuditTrailMiddleware`) was removed in 2026-09-01 because it
was overengineered and noisy. Logging is now plain `logging` with a single shared
logger plus a compliance-only audit channel.

**Status**: ✅ Migrated to standard logging

---

## Quick Start

Add logs to any module:

```python
from apps.app_base.logging_utils import logger, audit_logger

logger.debug("Detail trace")        # silent unless the farm logger is DEBUG
logger.info("Significant event")
logger.warning("Suspicious condition")
logger.error("Failure")
audit_logger.info("compliance_event | Entity:1 | user=officer")
```

---

## Loggers

| Logger | Use | File |
| --- | --- | --- |
| `farm` (via `logger`) | Regular application logging | `logs/debug.log` |
| `farm_audit` (via `audit_logger`) | Compliance events only | `logs/audit.log` |

`logger.debug(...)` is silent by default (`farm` logger is `INFO`). Raise the
level to `DEBUG` in `farm/settings.py` when tracing is needed.

---

## Documentation

- [DEBUG_QUICK_REFERENCE.md](DEBUG_QUICK_REFERENCE.md) — 2 minute reference
- [DEBUG_POINTS_INDEX.md](DEBUG_POINTS_INDEX.md) — technical index
- [DEBUG_IMPLEMENTATION_SUMMARY.md](DEBUG_IMPLEMENTATION_SUMMARY.md) — implementation notes
- Logging conventions: [../logging/LOGGING_STANDARDS.md](../logging/LOGGING_STANDARDS.md)

---

## Deleted components

- `apps/app_base/debug.py` (`DebugContext` + decorators)
- `apps/app_base/queryset_logging.py`
- `farm/middlewares_audit.py` (`AuditTrailMiddleware`)
- `farm_debug` logger
