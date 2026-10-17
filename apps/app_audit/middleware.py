"""Middleware that opens and closes an :class:`ActionTrace` per mutating request.

Every ``POST`` / ``PUT`` / ``PATCH`` / ``DELETE`` gets one trace, carrying the
submitted payload. The trace row is committed independently at request start,
so a failed action is still recorded even when the view's
``transaction.atomic()`` block rolls back its writes. The final status (success
or failure) is written once the block has exited.
"""

from . import context as provenance
from .models import TraceStatus

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class ActionTraceMiddleware:
    """Record a provenance trace around mutating requests."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not provenance.is_enabled() or request.method not in _MUTATING_METHODS:
            return self.get_response(request)

        trace = provenance.start_trace(request)
        token = provenance.set_trace(trace)
        try:
            response = self.get_response(request)
        except Exception as exc:
            provenance.finish_trace(
                trace,
                status=TraceStatus.FAILED,
                error=str(exc) or type(exc).__name__,
            )
            raise
        else:
            provenance.finish_trace(trace)
            return response
        finally:
            provenance.reset_trace(token)
