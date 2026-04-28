from functools import wraps
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin


def require_login(view_func):
    """Decorator to require login for function-based views."""
    return login_required(view_func)


class AuthRequiredMixin(LoginRequiredMixin):
    """Mixin for class-based views to require authentication."""
    pass
