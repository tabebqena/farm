# Debug Points Index

The project uses standard Python logging (see
[../logging/LOGGING_STANDARDS.md](../logging/LOGGING_STANDARDS.md)). Log points
are spread across models and views; below is the high-level coverage by area.

## Models

| File | Logging |
| --- | --- |
| `apps/app_transaction/models.py` | `clean()`/`create()` at debug; `reverse()` audit (`transaction_start`/`transaction_reversed`/`transaction_reversal_failed`) |
| `apps/app_adjustment/models.py` | `clean()`/`save()`/`delete()`/`finalize()`/`reverse()` at debug + `adjustment_*` audits |
| `apps/app_inventory/models.py` | `Product.clean()`/`save()`/`delete()` at debug + `product_*` audits |
| `apps/app_operation/models/operation.py` | `clean()`/`save()`/`delete()`/`reverse()` at debug + `operation_*` audits |
| `apps/app_entity/models/__init__.py` | entity/stakeholder/contact save/delete at debug + `entity_*`/`stakeholder_*`/`contact_info_*` audits |

## Views

| Area | Logging |
| --- | --- |
| `apps/app_entity/views/*` | entity/contact/stakeholder/category views: fetch + processing at debug, `*_created`/`*_updated`/`*_failed` audits |
| `apps/app_operation/views/*` | operation detail/list/edit/period/reverse/record views: fetch + processing at debug, reversal/creation audits |
| `apps/app_operation/views/create_operation/*` | create views (base/birth/death/evaluation/wizards): setup + creation at debug, `operation_created`/`operation_creation_failed` audits |
| `apps/app_transaction/views.py` | transaction list/detail/reverse: fetch + processing at debug, reversal audits |
| `apps/app_report/views.py` | report scope resolution at debug |

## Forms

All forms inherit `apps.app_base.form_logging.LoggingFormMixin`:
- `clean()` logs at debug; validation errors log a warning.
- `save(commit=True)` emits a `form_create`/`form_update` audit line.

## Configuring levels

The `farm` logger is `INFO` by default. To trace, set it to `DEBUG` in
`farm/settings.py`. The `farm_audit` logger always writes to `logs/audit.log`.
