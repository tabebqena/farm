# Comprehensive Logging Implementation

## Status

The custom debug/audit layer was replaced with standard Python logging on
2026-09-01 (see `ai-plans/replace-debug-with-standard-logging-plan.md`).

- Removed: `apps/app_base/debug.py` (`DebugContext`, decorators),
  `apps/app_base/queryset_logging.py`, `farm/middlewares_audit.py`
  (`AuditTrailMiddleware`), and the `farm_debug` logger.
- Kept: `apps/app_base/logging_utils.py` exposes the shared `farm` logger and
  the `farm_audit` compliance logger.
- Kept: `apps/app_base/form_logging.py` (`LoggingFormMixin`), rewritten on
  standard logging.

## Where logging lives now

| Area | Logger | Examples |
| --- | --- | --- |
| Models (validation, save/delete) | `logger` (mostly `debug`) | entity/operation/adjustment/product save/delete |
| Model compliance events | `audit_logger` (`info`/`error`) | create/update/delete of key records, reversals |
| Views (setup, fetches, processing) | `logger` (`debug`) | view setup, entity fetches, form processing |
| View compliance events | `audit_logger` (`info`/`error`) | operation created/reversed, period closed, form audits |
| Forms (`LoggingFormMixin`) | `logger` (`debug`) + `audit_logger` | form validation, form save audit |

## Example: a view after migration

```python
from apps.app_base.logging_utils import audit_logger, logger

def my_view(request, pk):
    logger.debug(f"Fetching entity | entity_pk={pk}")
    entity = get_object_or_404(Entity, pk=pk, error_message="Entity not found.")
    logger.debug(f"Entity loaded | entity_id={entity.pk}")

    if request.method == "POST":
        try:
            entity.save()
            audit_logger.info(f"entity_updated | Entity:{entity.pk} | "
                              f"user={request.user.username}")
            return redirect("success")
        except Exception as e:
            logger.error(f"Entity update failed | error={e}")
            audit_logger.error(f"entity_update_failed | Entity:{entity.pk} | error={e}")
    return render(request, "template.html", {"entity": entity})
```

## Deleted files / modules

- `apps/app_base/debug.py`
- `apps/app_base/queryset_logging.py`
- `farm/middlewares_audit.py`
- `farm_debug` logger entry in `farm/settings.py`
