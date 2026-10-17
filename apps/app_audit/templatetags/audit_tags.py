"""Template helpers for linking a record to its provenance history."""

from django import template
from django.urls import reverse

register = template.Library()


@register.simple_tag
def record_history_url(obj):
    """Return the audit "why does this row exist?" URL for *obj*, or ``""``.

    Proxy instances resolve to their concrete model so all operation types share
    one history page. Never raises — a missing URL just hides the link.
    """
    try:
        meta = getattr(obj, "_meta", None)
        if meta is None or getattr(obj, "pk", None) is None:
            return ""
        concrete = meta.concrete_model or type(obj)
        cmeta = concrete._meta
        return reverse(
            "audit_record_history",
            args=[cmeta.app_label, cmeta.model_name, str(obj.pk)],
        )
    except Exception:
        return ""
