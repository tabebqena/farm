"""
Centralized debug logging utilities for the Farm application.

Provides structured logging with context awareness, performance tracking, and audit trails.
"""

import json
import logging
import sys
import time
import traceback
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from django.conf import settings

_TEST_MODE_CACHE: Optional[bool] = None

def _in_test_mode() -> bool:
    global _TEST_MODE_CACHE
    if _TEST_MODE_CACHE is None:
        _TEST_MODE_CACHE = (
            "pytest" in sys.modules
            or (len(sys.argv) > 1 and sys.argv[1] == "test")
        )
    return _TEST_MODE_CACHE

logger = logging.getLogger("farm_debug")
audit_logger = logging.getLogger("farm_audit")

# Configure audit logger for file-based persistence
_audit_handler_configured = False
def _configure_audit_handler():
    if _in_test_mode():
        return
    global _audit_handler_configured
    if not _audit_handler_configured:
        log_dir = Path(settings.BASE_DIR) / "logs"
        log_dir.mkdir(exist_ok=True)

        audit_file = log_dir / "audit.log"
        file_handler = logging.FileHandler(audit_file)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        audit_logger.addHandler(file_handler)
        audit_logger.setLevel(logging.INFO)
        _audit_handler_configured = True


class DebugContext:
    """Context manager for debug logging with indentation and timing."""

    _depth = 0
    _timings: Dict[str, float] = {}

    @classmethod
    def _indent(cls) -> str:
        return "  " * cls._depth

    @classmethod
    @contextmanager
    def section(cls, title: str, data: Optional[Dict[str, Any]] = None):
        """Context manager for logging a section with automatic indentation and timing."""
        if _in_test_mode():
            yield
            return
        cls._depth += 1
        indent = cls._indent()
        prefix = f"→ {title}"

        if data:
            logger.info(f"{indent}{prefix} | {cls._format_data(data)}")
        else:
            logger.info(f"{indent}{prefix}")

        start_time = time.time()
        try:
            yield
        finally:
            elapsed = time.time() - start_time
            cls._depth -= 1
            indent = cls._indent()
            logger.info(f"{indent}← {title} ({elapsed:.3f}s)")

    @classmethod
    def log(cls, message: str, data: Optional[Dict[str, Any]] = None, level: str = "info"):
        """Log a message with optional data."""
        if _in_test_mode():
            return
        indent = cls._indent()
        prefix = "⚡"

        if data:
            logger.log(
                getattr(logging, level.upper()),
                f"{indent}{prefix} {message} | {cls._format_data(data)}",
            )
        else:
            logger.log(getattr(logging, level.upper()), f"{indent}{prefix} {message}")

    @classmethod
    def error(cls, message: str, exception: Optional[Exception] = None, data: Optional[Dict[str, Any]] = None):
        """Log an error with optional exception and data."""
        if _in_test_mode():
            return
        indent = cls._indent()
        prefix = "❌"

        msg = f"{indent}{prefix} {message}"
        if data:
            msg += f" | {cls._format_data(data)}"
        if exception:
            msg += f" | {exception.__class__.__name__}: {str(exception)}"

        logger.error(msg)

    @classmethod
    def warn(cls, message: str, data: Optional[Dict[str, Any]] = None):
        """Log a warning."""
        cls.log(message, data, level="warning")

    @classmethod
    def success(cls, message: str, data: Optional[Dict[str, Any]] = None):
        """Log a success message."""
        if _in_test_mode():
            return
        indent = cls._indent()
        prefix = "✓"
        if data:
            logger.info(f"{indent}{prefix} {message} | {cls._format_data(data)}")
        else:
            logger.info(f"{indent}{prefix} {message}")

    @classmethod
    def _format_data(cls, data: Dict[str, Any]) -> str:
        """Format data for logging."""
        try:
            return json.dumps(data, indent=0, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            return repr(data)

    @classmethod
    def audit(cls, action: str, entity_type: str, entity_id: Any, details: Optional[Dict[str, Any]] = None, user: Optional[str] = None):
        """Log an audit event for compliance and tracing."""
        if _in_test_mode():
            return
        _configure_audit_handler()
        audit_data = {
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "timestamp": datetime.now().isoformat(),
            "user": user or "system",
        }
        if details:
            audit_data["details"] = details

        audit_logger.info(json.dumps(audit_data, default=str, ensure_ascii=False))
        cls.log(f"[AUDIT] {action} on {entity_type}:{entity_id}", details, level="info")

    @classmethod
    def transaction_start(cls, transaction_id: str, description: str, data: Optional[Dict[str, Any]] = None):
        """Log the start of a financial or data transaction."""
        if _in_test_mode():
            return
        _configure_audit_handler()
        indent = cls._indent()
        msg = f"{indent}🔄 TRANSACTION START | {transaction_id} | {description}"
        if data:
            msg += f" | {cls._format_data(data)}"
        logger.info(msg)

        audit_data = {
            "event": "transaction_start",
            "transaction_id": transaction_id,
            "description": description,
            "timestamp": datetime.now().isoformat(),
        }
        if data:
            audit_data["data"] = data
        audit_logger.info(json.dumps(audit_data, default=str, ensure_ascii=False))

    @classmethod
    def transaction_commit(cls, transaction_id: str, result: Optional[Dict[str, Any]] = None):
        """Log successful transaction completion."""
        if _in_test_mode():
            return
        _configure_audit_handler()
        indent = cls._indent()
        msg = f"{indent}✓ TRANSACTION COMMIT | {transaction_id}"
        if result:
            msg += f" | {cls._format_data(result)}"
        logger.info(msg)

        audit_data = {
            "event": "transaction_commit",
            "transaction_id": transaction_id,
            "timestamp": datetime.now().isoformat(),
        }
        if result:
            audit_data["result"] = result
        audit_logger.info(json.dumps(audit_data, default=str, ensure_ascii=False))

    @classmethod
    def transaction_rollback(cls, transaction_id: str, reason: str, exception: Optional[Exception] = None):
        """Log transaction failure and rollback."""
        if _in_test_mode():
            return
        _configure_audit_handler()
        indent = cls._indent()
        msg = f"{indent}❌ TRANSACTION ROLLBACK | {transaction_id} | {reason}"
        if exception:
            msg += f" | {exception.__class__.__name__}: {str(exception)}"
        logger.error(msg)

        audit_data = {
            "event": "transaction_rollback",
            "transaction_id": transaction_id,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        }
        if exception:
            audit_data["exception"] = {
                "type": exception.__class__.__name__,
                "message": str(exception),
            }
        audit_logger.error(json.dumps(audit_data, default=str, ensure_ascii=False))


def debug_function(func: Callable) -> Callable:
    """Decorator to add automatic debug logging to a function."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        func_name = func.__qualname__
        args_info = {
            "args": [repr(arg)[:100] for arg in args[:3]],  # limit repr
            "kwargs_keys": list(kwargs.keys()),
        }

        with DebugContext.section(f"🔵 {func_name}", args_info):
            try:
                result = func(*args, **kwargs)
                DebugContext.success(f"{func_name} completed")
                return result
            except Exception as e:
                DebugContext.error(f"{func_name} failed", e)
                raise

    return wrapper


def debug_model_save(method_name: str = "save"):
    """Decorator for model save/create methods."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            model_name = self.__class__.__name__
            pk = getattr(self, "pk", None)
            state = "update" if pk else "create"

            data = {
                "model": model_name,
                "pk": pk,
                "action": state,
                "fields": list(kwargs.get("update_fields", [])),
            }

            with DebugContext.section(f"💾 {model_name}.{method_name} ({state})", data):
                try:
                    result = func(self, *args, **kwargs)
                    DebugContext.success(f"{model_name} {state} completed", {"pk": self.pk})
                    return result
                except Exception as e:
                    DebugContext.error(f"{model_name} {state} failed", e)
                    raise

        return wrapper

    return decorator


def debug_view(view_func: Callable) -> Callable:
    """Decorator for Django views."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        view_name = view_func.__name__
        request_data = {
            "method": request.method,
            "path": request.path,
            "user": getattr(request.user, "username", "anonymous"),
            "GET_params": dict(request.GET),
            "POST_keys": list(request.POST.keys())[:5],  # limit for brevity
        }

        with DebugContext.section(f"🌐 {view_name}", request_data):
            try:
                response = view_func(request, *args, **kwargs)
                status_code = getattr(response, "status_code", "unknown")
                DebugContext.success(f"{view_name} completed", {"status_code": status_code})
                return response
            except Exception as e:
                DebugContext.error(f"{view_name} failed", e)
                raise

    return wrapper


def debug_signal(signal_name: str):
    """Decorator for Django signal handlers."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(sender, **kwargs):
            sender_name = sender.__name__ if hasattr(sender, "__name__") else str(sender)
            signal_data = {
                "signal": signal_name,
                "sender": sender_name,
                "kwargs_keys": list(kwargs.keys()),
            }

            with DebugContext.section(f"📡 {signal_name} ({sender_name})", signal_data):
                try:
                    result = func(sender, **kwargs)
                    DebugContext.success(f"{signal_name} handler completed")
                    return result
                except Exception as e:
                    DebugContext.error(f"{signal_name} handler failed", e)
                    raise

        return wrapper

    return decorator


def debug_db_operation(operation_type: str = "operation"):
    """Decorator for database-level operations (QuerySet modifications)."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            model_name = self.model.__name__ if hasattr(self, "model") else "Unknown"
            func_name = func.__name__
            op_data = {
                "model": model_name,
                "operation": func_name,
                "type": operation_type,
                "args_count": len(args),
            }

            with DebugContext.section(f"🗄️ {model_name}.{func_name}", op_data):
                try:
                    result = func(self, *args, **kwargs)
                    DebugContext.success(f"{func_name} completed on {model_name}", {"result_type": type(result).__name__})
                    return result
                except Exception as e:
                    DebugContext.error(f"{func_name} failed on {model_name}", e)
                    raise

        return wrapper

    return decorator


def debug_transaction(transaction_type: str = "financial"):
    """Decorator for transaction-level operations (multi-step, atomic)."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            import uuid
            txn_id = f"{func.__qualname__}_{uuid.uuid4().hex[:8]}"
            user = getattr(self, "officer", None) or getattr(self, "user", None)
            user_str = str(user) if user else "system"

            txn_data = {
                "type": transaction_type,
                "args_count": len(args),
                "user": user_str,
            }

            DebugContext.transaction_start(txn_id, f"{func.__qualname__}", txn_data)

            try:
                result = func(self, *args, **kwargs)
                DebugContext.transaction_commit(txn_id, {"status": "success", "result_pk": getattr(result, "pk", None)})
                DebugContext.audit(
                    action=f"transaction_{transaction_type}",
                    entity_type=self.__class__.__name__,
                    entity_id=getattr(self, "pk", None),
                    details={"transaction_id": txn_id, "user": user_str},
                    user=user_str
                )
                return result
            except Exception as e:
                DebugContext.transaction_rollback(txn_id, str(e), e)
                DebugContext.audit(
                    action=f"transaction_{transaction_type}_failed",
                    entity_type=self.__class__.__name__,
                    entity_id=getattr(self, "pk", None),
                    details={"transaction_id": txn_id, "error": str(e), "user": user_str},
                    user=user_str
                )
                raise

        return wrapper

    return decorator
