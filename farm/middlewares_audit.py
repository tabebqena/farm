"""
Audit trail middleware for request/response tracking.
Logs all HTTP operations for compliance and debugging.
"""

import json
import logging
import time
from django.utils.deprecation import MiddlewareMixin

audit_logger = logging.getLogger("farm_audit")
logger = logging.getLogger("farm_debug")


class AuditTrailMiddleware(MiddlewareMixin):
    """Middleware to audit all HTTP requests and responses."""

    def process_request(self, request):
        """Log incoming request."""
        request._audit_start_time = time.time()

        # Skip static files and health checks
        if request.path.startswith("/static/"):
            return None

        request_data = {
            "event": "request_start",
            "method": request.method,
            "path": request.path,
            "user": getattr(request.user, "username", "anonymous"),
            "ip_address": self._get_client_ip(request),
            "timestamp": time.time(),
        }

        if request.method in ["POST", "PUT", "PATCH"]:
            request_data["post_keys"] = list(request.POST.keys())[:10]

        audit_logger.info(json.dumps(request_data, default=str, ensure_ascii=False))
        return None

    def process_response(self, request, response):
        """Log completed response."""
        if not hasattr(request, "_audit_start_time"):
            return response

        if request.path.startswith("/static/"):
            return response

        elapsed = time.time() - request._audit_start_time

        response_data = {
            "event": "request_complete",
            "method": request.method,
            "path": request.path,
            "user": getattr(request.user, "username", "anonymous"),
            "status_code": response.status_code,
            "elapsed_ms": round(elapsed * 1000, 2),
            "timestamp": time.time(),
        }

        # Log errors more prominently
        if response.status_code >= 400:
            audit_logger.warning(json.dumps(response_data, default=str, ensure_ascii=False))
        else:
            audit_logger.info(json.dumps(response_data, default=str, ensure_ascii=False))

        return response

    def process_exception(self, request, exception):
        """Log exceptions during request processing."""
        if not hasattr(request, "_audit_start_time"):
            return None

        elapsed = time.time() - request._audit_start_time

        error_data = {
            "event": "request_exception",
            "method": request.method,
            "path": request.path,
            "user": getattr(request.user, "username", "anonymous"),
            "exception": exception.__class__.__name__,
            "message": str(exception),
            "elapsed_ms": round(elapsed * 1000, 2),
            "timestamp": time.time(),
        }

        audit_logger.error(json.dumps(error_data, default=str, ensure_ascii=False))
        return None

    @staticmethod
    def _get_client_ip(request):
        """Extract client IP from request."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip
