from django.shortcuts import redirect
from django.urls import reverse


class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # Cache exempt URL patterns
        self._exempt_patterns = None

    def get_exempt_patterns(self):
        if self._exempt_patterns is None:
            self._exempt_patterns = [
                reverse("login"),
                reverse("admin:index"),
                reverse("register"),
                "/i18n/",  # Language switching endpoint
            ]
        return self._exempt_patterns

    def __call__(self, request):
        if not request.user.is_authenticated:
            exempt_patterns = self.get_exempt_patterns()

            # Check if the current path matches any exempt pattern
            is_exempt = any(
                request.path == pattern or
                request.path.startswith(pattern)
                for pattern in exempt_patterns
            )

            if not is_exempt:
                return redirect(f"{reverse('login')}?next={request.path}")

        return self.get_response(request)
