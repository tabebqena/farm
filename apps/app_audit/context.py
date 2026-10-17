"""Request-scoped provenance runtime.

``BaseModel.save()`` calls :func:`record_save` for every write. When a mutating
request is being traced, that write is attached to the running
:class:`~apps.app_audit.models.ActionTrace`; a surrounding :func:`derived`
block tags the write as *auto-created* and records the rule that produced it.

Everything here is a no-op when tracking is disabled (``FARM_TRACKING_ENABLED``)
or when there is no active trace, and it never raises into the write it
observes.
"""

import contextlib
import contextvars
import logging

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("farm")

_current_trace = contextvars.ContextVar("audit_current_trace", default=None)
_current_role = contextvars.ContextVar("audit_current_role", default=None)
_current_reason = contextvars.ContextVar("audit_current_reason", default=None)
_current_origin = contextvars.ContextVar("audit_current_origin", default="model")

# POST keys that must never be persisted verbatim in the trace payload.
_REDACTED_FIELDS = {"csrfmiddlewaretoken", "password", "password1", "password2"}


def is_enabled() -> bool:
    """Whether provenance tracking is switched on for this process."""
    return bool(getattr(settings, "FARM_TRACKING_ENABLED", True))


def get_current_trace():
    """The :class:`ActionTrace` for the running request, or ``None``."""
    return _current_trace.get()


# --------------------------------------------------------------------------- #
# Trace lifecycle (driven by the middleware)
# --------------------------------------------------------------------------- #
def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def sanitize_payload(request) -> dict:
    """Turn ``request.POST`` into a JSON-safe ``{field: [values]}`` map."""
    payload = {}
    try:
        items = request.POST.lists()
    except Exception:
        return payload
    for key, values in items:
        if key in _REDACTED_FIELDS:
            payload[key] = ["<redacted>"]
            continue
        safe = []
        for value in values:
            try:
                safe.append(str(value)[:2000])
            except Exception:
                safe.append("<unserializable>")
        payload[key] = safe
    if getattr(request, "FILES", None):
        payload["__files__"] = list(request.FILES.keys())
    return payload


def start_trace(request):
    """Create and return the :class:`ActionTrace` for *request* (or ``None``)."""
    if not is_enabled():
        return None
    from .models import ActionTrace, TraceStatus

    user = getattr(request, "user", None)
    actor = user if (user is not None and user.is_authenticated) else None
    resolver = getattr(request, "resolver_match", None)
    action = getattr(resolver, "view_name", "") if resolver else ""
    group_key = ""
    try:
        group_key = request.session.get("audit_group_key", "") or ""
    except Exception:
        group_key = ""
    try:
        return ActionTrace.objects.create(
            actor=actor,
            method=request.method,
            path=(request.path or "")[:512],
            action=action or "",
            payload=sanitize_payload(request),
            status=TraceStatus.IN_PROGRESS,
            group_key=group_key,
            ip=_client_ip(request),
        )
    except Exception:
        logger.exception("audit: failed to start trace")
        return None


def set_trace(trace):
    """Bind *trace* as the active trace; returns a reset token."""
    return _current_trace.set(trace)


def reset_trace(token):
    """Restore the previously active trace."""
    _current_trace.reset(token)


def set_root(obj):
    """Point the active trace at the top-level record the action created."""
    trace = _current_trace.get()
    if trace is None or obj is None:
        return
    meta = getattr(obj, "_meta", None)
    if meta is None:
        return
    concrete = getattr(meta, "concrete_model", None) or obj.__class__
    cmeta = concrete._meta
    trace.root_app = cmeta.app_label
    trace.root_model = cmeta.model_name
    trace.root_pk = str(obj.pk)


def mark_failed(trace, error, *, field=None, value=None):
    """Record that the traced action failed (held in memory, saved by the middleware).

    Because the surrounding ``transaction.atomic()`` block may still roll back,
    the failure is not written here; the middleware persists the final state
    once the block has exited.
    """
    from .models import TraceStatus

    if trace is None:
        return
    trace.status = TraceStatus.FAILED
    parts = []
    if field:
        parts.append(f"field={field}")
    if value is not None:
        parts.append(f"value={value!r}")
    if parts:
        parts.append(str(error))
        trace.error = " | ".join(parts)[:5000]
    else:
        trace.error = str(error)[:5000]


def record_validation_error(error, *, field=None, value=None):
    """Convenience wrapper around :func:`mark_failed` for the active trace."""
    mark_failed(_current_trace.get(), error, field=field, value=value)


def finish_trace(trace, *, status=None, error="", root=None):
    """Persist the final state of *trace* (called by the middleware)."""
    if trace is None:
        return
    from .models import TraceStatus

    if root is not None:
        set_root(root)
    if status is not None:
        trace.status = status
    elif trace.status == TraceStatus.IN_PROGRESS:
        trace.status = TraceStatus.SUCCESS
    if error and not trace.error:
        trace.error = str(error)[:5000]
    try:
        if trace.created_at is not None:
            elapsed = timezone.now() - trace.created_at
            trace.duration_ms = max(0, int(elapsed.total_seconds() * 1000))
    except Exception:
        pass
    try:
        trace.save(
            update_fields=[
                "status",
                "error",
                "root_app",
                "root_model",
                "root_pk",
                "duration_ms",
            ]
        )
    except Exception:
        logger.exception("audit: failed to finish trace %s", getattr(trace, "pk", None))


# --------------------------------------------------------------------------- #
# Derived (auto-created) marking
# --------------------------------------------------------------------------- #
@contextlib.contextmanager
def derived(role, reason_code=None, origin="model"):
    """Mark every save performed inside this block as auto-created.

    *role* names what the row is (e.g. ``ISSUANCE_TXN``); *reason_code* points
    into :mod:`apps.app_audit.reasons` for the human explanation.
    """
    role_token = _current_role.set(role)
    reason_token = _current_reason.set(reason_code)
    origin_token = _current_origin.set(origin)
    try:
        yield
    finally:
        _current_role.reset(role_token)
        _current_reason.reset(reason_token)
        _current_origin.reset(origin_token)


# --------------------------------------------------------------------------- #
# The central save hook (called from BaseModel.save / delete)
# --------------------------------------------------------------------------- #
def record_save(instance, kind, origin=None):
    """Record one model save into the audit trail.

    Safe to call for every save: it is a no-op when tracking is off, when the
    instance belongs to this app, or when no :class:`SaveLog` can be built.
    """
    if not is_enabled():
        return
    meta = getattr(instance, "_meta", None)
    if meta is None or meta.app_label == "app_audit":
        return
    # Proxy models have no table of their own: record them under their concrete
    # model so one record's history is not split across proxy names.
    concrete = (meta.concrete_model or instance.__class__)._meta

    from .models import SaveLog
    from .reasons import reason_text
    from .serialization import serialize_instance

    trace = _current_trace.get()
    role = _current_role.get()
    reason = _current_reason.get()
    try:
        SaveLog.objects.create(
            trace=trace,
            actor=getattr(trace, "actor", None) if trace is not None else None,
            app_label=concrete.app_label,
            model=concrete.model_name,
            object_id=str(instance.pk),
            object_repr=str(instance)[:255],
            kind=kind,
            new_shape=serialize_instance(instance),
            is_derived=role is not None,
            role=role or "",
            reason_code=reason or "",
            reason_text=reason_text(reason),
            origin=origin or _current_origin.get(),
        )
    except Exception:
        logger.exception("audit: failed to record save for %s", instance)
