from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect, render
from django.views import View

from .forms import UserProfileForm


class LoginView(auth_views.LoginView):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            next_url = request.GET.get("next") or settings.LOGIN_REDIRECT_URL
            return redirect(next_url)
        return super().dispatch(request, *args, **kwargs)


class ProfileView(View):
    """Show the current user's profile (read-only detail page)."""

    def get(self, request, *args, **kwargs):
        return render(request, "registration/profile.html")


class ProfileEditView(View):
    """Edit the current user's profile."""

    def get(self, request, *args, **kwargs):
        form = UserProfileForm(instance=request.user)
        return render(request, "registration/profile_edit.html", {"form": form})

    def post(self, request, *args, **kwargs):
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect("profile")
        return render(request, "registration/profile_edit.html", {"form": form})
