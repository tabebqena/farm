from django.shortcuts import render, redirect
from django.contrib.auth import views as auth_views
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.conf import settings
from .forms import UserProfileForm


class LoginView(auth_views.LoginView):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            next_url = request.GET.get("next") or settings.LOGIN_REDIRECT_URL
            return redirect(next_url)
        return super().dispatch(request, *args, **kwargs)


@require_http_methods(["GET"])
def profile(request):
    """Show the current user's profile (read-only detail page)."""
    return render(request, 'registration/profile.html')


@require_http_methods(["GET", "POST"])
def profile_edit(request):
    """Edit the current user's profile."""
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile')
    else:
        form = UserProfileForm(instance=request.user)
    return render(request, 'registration/profile_edit.html', {'form': form})
