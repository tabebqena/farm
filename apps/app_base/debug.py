"""
Centralized debug logging utilities for the Farm application.

Provides structured logging with context awareness and performance tracking.
"""

import json
import logging
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("farm_debug")


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
