"""JSON-safe serialization of a model instance's *new shape*.

``serialize_instance`` produces a flat ``{field_name: value}`` map of a model's
concrete fields after a save. It is used by :class:`SaveLog` to store the full
post-save row, so the audit trail is self-contained and never has to re-read a
row that may later be soft-deleted.

It must never raise (a logging helper must not break the write it observes), so
every value is coerced defensively with a ``str()`` fallback.
"""

import datetime
import decimal
import uuid

# Long text values are truncated so a single oversized field cannot bloat the
# audit table.
_MAX_STR = 8000
_MAX_LIST = 200


def _json_safe(value):
    """Coerce *value* into something :class:`~django.db.models.JSONField` accepts."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:_MAX_STR]
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (uuid.UUID,)):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<bytes:{len(value)}>"
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in list(value)[:_MAX_LIST]]
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in list(value.items())[:_MAX_LIST]}
    return str(value)


def serialize_instance(obj) -> dict:
    """Return the concrete fields of *obj* as a JSON-safe ``{name: value}`` map.

    Foreign keys are stored as ``{"model": "app.Model", "pk": ...}`` without any
    extra query; many-to-many and reverse relations are skipped (they are not
    part of the row's own shape).
    """
    data = {}
    try:
        fields = obj._meta.concrete_fields
    except Exception:
        return data

    for field in fields:
        try:
            if field.is_relation and field.many_to_many:
                continue
            raw = field.value_from_object(obj)
            if field.is_relation:
                related = field.related_model
                data[field.name] = {
                    "model": related._meta.label_lower if related else "",
                    "pk": _json_safe(raw),
                }
            else:
                data[field.name] = _json_safe(raw)
        except Exception:
            try:
                data[field.name] = str(getattr(obj, field.name, ""))
            except Exception:
                data[field.name] = "<unserializable>"
    return data
