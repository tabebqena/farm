# Logging Implementation Guide

This guide shows how to add standard Python logging to Farm modules using the
shared loggers from [`apps/app_base/logging_utils.py`](../../apps/app_base/logging_utils.py).

## Imports

```python
from apps.app_base.logging_utils import logger, audit_logger
```

- `logger` — the project-wide `farm` logger (`debug`/`info`/`warning`/`error`).
- `audit_logger` — the compliance-only `farm_audit` logger (`logs/audit.log`),
  for create/update/delete of key records, reversals, and period close.

## Models

Regular steps and validation use `logger.debug(...)` (silent by default).
Failures use `logger.error(...)`. Compliance events use `audit_logger.info(...)`.

```python
def save(self, *args, **kwargs):
    action = "updated" if self.pk else "created"
    result = super().save(*args, **kwargs)
    logger.debug(f"{self.__class__.__name__} {action} | pk={self.pk}")
    audit_logger.info(f"{self.__class__.__name__.lower()}_{action} | {self.__class__.__name__}:{self.pk} | "
                      f"user={getattr(self, 'officer', 'system')}")
    return result
```

## Views

No decorators are used. Log the meaningful steps explicitly.

```python
def my_view(request, pk):
    logger.debug(f"Fetching entity | entity_pk={pk} | user={request.user.username}")
    entity = get_object_or_404(Entity, pk=pk, error_message="Entity not found.")
    logger.debug(f"Entity loaded | entity_id={entity.pk}")

    if request.method == "POST":
        form = MyForm(request.POST)
        if form.is_valid():
            instance = form.save()
            audit_logger.info(f"entity_created | Entity:{instance.pk} | "
                              f"user={request.user.username}")
            return redirect("success_url")
        logger.warning(f"Form validation failed | {form.errors}")
    return render(request, "template.html", {"form": form})
```

## Forms

Forms inherit [`apps/app_base/form_logging.py`](../../apps/app_base/form_logging.py)
(`LoggingFormMixin`), which logs at `debug` level and emits a
`form_create`/`form_update` audit line on commit. No per-form logging code is
required.

## Reversals / transactions

Use `audit_logger.info(...)` for the start/commit and `audit_logger.error(...)`
for failures, keeping the existing `action` strings (e.g. `transaction_reversed`,
`operation_reversal_failed`) so `logs/audit.log` stays consistent.

## Enabling DEBUG traces

`logger.debug(...)` calls are silent because the `farm` logger defaults to
`INFO` in [`farm/settings.py`](../../farm/settings.py). To trace, temporarily set:

```python
"farm": {"handlers": ["console", "debug_file"], "level": "DEBUG", "propagate": False},
```

## Verification

- `manage.py check`
- `manage.py test apps --parallel=10 --keepdb`

See [`docs/logging/LOGGING_STANDARDS.md`](LOGGING_STANDARDS.md) for conventions.
