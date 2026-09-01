# Debug Quick Reference

## Import

```python
from apps.app_base.logging_utils import logger, audit_logger
```

## Logging levels

```python
logger.debug("Detail")     # silent unless farm logger is DEBUG
logger.info("Event")
logger.warning("Warning")
logger.error("Error")
```

## Compliance / audit

```python
audit_logger.info(f"entity_created | Entity:{entity.pk} | user={request.user.username}")
audit_logger.error(f"operation_reversal_failed | Operation:{op.pk} | error={e}")
```

Use `audit_logger` only for create/update/delete of key records, reversals, and
period close.

## Best practices

- Keep `logger.debug(...)` for fine-grained steps — it is silent by default.
- Convert objects to primitives before logging: `str(obj)`, `obj.pk`, `float(x)`.
- Preserve the existing audit `action` strings (e.g. `transaction_reversed`,
  `period_closed`) so `logs/audit.log` stays consistent.

## Enabling debug output

```python
# farm/settings.py — temporarily
"farm": {"handlers": ["console", "debug_file"], "level": "DEBUG", "propagate": False},
```

## Verifying

```bash
tail -f logs/debug.log   # application log
tail -f logs/audit.log   # compliance log
```
