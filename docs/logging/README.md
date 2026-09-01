# Logging Documentation

- [Logging Standards](LOGGING_STANDARDS.md) - Logging standards and conventions
- [Logging Implementation Guide](LOGGING_IMPLEMENTATION_GUIDE.md) - How to implement logging

## Quick summary

The project uses **standard Python logging** (`logging.getLogger`) with two channels:

1. **`farm` logger** — one project-wide logger for regular application logging
   (`debug`/`info`/`warning`/`error`), configured at `INFO` by default so
   `logger.debug(...)` calls stay silent unless tracing is enabled.
2. **`farm_audit` logger** — a compliance-only channel (routed to
   `logs/audit.log`) used exclusively for create/update/delete of key records,
   reversals, and period close.

Both loggers are exposed from `apps/app_base/logging_utils.py`:
`from apps.app_base.logging_utils import logger, audit_logger`.

See `docs/logging/LOGGING_STANDARDS.md` for the full conventions.
