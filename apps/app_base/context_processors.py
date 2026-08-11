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

    # Apply navigation overrides from the view.
    # An override value can be:
    #   - a URL string          -> replace only the link URL
    #   - a dict {title, url}   -> replace both the label and the URL
    #   - None                  -> drop the related view entirely
    # Related views that have no override entry are left untouched.
    overrides = getattr(request, 'navigation_overrides', {})
    if overrides:
        related_url_overrides = overrides.get('related_urls', {})
        related_views = []
        for item in nav_context.get('related_views', []):
            if item['title'] not in related_url_overrides:
                related_views.append(item)
                continue
            override = related_url_overrides[item['title']]
            if override is None:
                continue
            if isinstance(override, dict):
                item['title'] = override.get('title', item['title'])
                item['url'] = override.get('url', item['url'])
            else:
                item['url'] = override
            related_views.append(item)
        # Views may append extra related views (e.g. per-entity operations links).
        # Each entry is a dict with 'title' and 'url'.
        related_views.extend(overrides.get('add_related', []))
        nav_context['related_views'] = related_views

    return nav_context
