"""
URL configuration for farm project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView
from apps.app_base.views import LoginView

from . import views as error_views

urlpatterns = [
    # Language-switching endpoint (not wrapped in i18n_patterns)
    path("i18n/", include("django.conf.urls.i18n")),
]

urlpatterns += i18n_patterns(
    path("admin/", admin.site.urls),
    path("entities/", include("apps.app_entity.urls")),
    path("entities/operations/", include("apps.app_operation.urls")),
    path("inventory/", include("apps.app_inventory.urls")),
    path("auth/", include("apps.app_base.urls")),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # Todo: dashboard view
    path("", RedirectView.as_view(pattern_name="entity_list", permanent=False)),
    prefix_default_language=True,
)

# Custom error handlers
handler404 = error_views.handler404
handler500 = error_views.handler500
handler403 = error_views.handler403
handler400 = error_views.handler400
