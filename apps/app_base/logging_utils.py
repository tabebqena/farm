"""Shared logging handles for the Farm project.

One project-wide logger plus a dedicated compliance/audit channel.
Both are configured in ``farm/settings.py`` LOGGING.
"""

import logging

# One logger for the whole project. Configured at INFO by default so
# ``logger.debug(...)`` calls stay silent unless tracing is enabled.
logger = logging.getLogger("farm")

# Compliance-only channel, routed to ``logs/audit.log``.
# Used for create/update/delete of key records, reversals, and period close.
audit_logger = logging.getLogger("farm_audit")


def build_error_details(exc, *, extra=None, user=None):
    """Build the standard ``error_details`` dict shared across error handlers.

    The dict always includes ``exception_type`` and ``error_message`` derived
    from *exc*, plus any *extra* keys and (optionally) ``user`` (resolved from
    ``request.user`` or a username string). Callers pass the same keys/order
    they previously built inline so the resulting log output stays identical.

    Returns the dict so callers can embed it in audit messages, flash
    ``messages.error(...)``, or re-render context.
    """
    details = {
        "exception_type": type(exc).__name__,
        "error_message": str(exc),
    }
    if extra:
        details.update(extra)
    if user is not None:
        details["user"] = getattr(user, "username", str(user))
    return details
