from django.shortcuts import redirect
from django.urls import reverse


class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # List of URLs that don't require login (like the login page itself!)
        exempt_urls = [reverse("login"), reverse("admin:index")]

        if not request.user.is_authenticated and request.path not in exempt_urls:
            return redirect(f"{reverse('login')}?next={request.path}")

        return self.get_response(request)
