"""Context processors for injecting common data into templates."""

from django.urls import resolve, Resolver404
from apps.app_base.navigation import get_navigation_context


def navigation(request):
    """
    Inject navigation context into all templates.

    Automatically detects the current view and provides parent/related views navigation.
    """
    try:
        resolver_match = resolve(request.path)
        current_view_name = resolver_match.url_name
        view_kwargs = resolver_match.kwargs
    except (Resolver404, AttributeError):
        return {'show_navigation': False}

    # Get navigation context for the current view
    nav_context = get_navigation_context(current_view_name, view_kwargs)

    return nav_context
