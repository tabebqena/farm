"""Navigation configuration and helpers for the application."""

from django.urls import reverse

NAVIGATION_MAP = {
    # Entity views
    'entity_list': {
        'title': 'Entities',
        'icon': 'bi-person-badge',
        'breadcrumb': [('Entities', 'entity_list')],
        'related': [],
    },
    'entity_detail': {
        'title': 'Entity Detail',
        'icon': 'bi-person-circle',
        'parent': ('Entities', 'entity_list'),
        'related': [
            ('Operations', 'operation_list_view', {'person_pk': 'pk'}),
            ('Periods', 'period_list_view', {'entity_pk': 'pk'}),
            ('Edit', 'person_edit', {'pk': 'pk'}),
        ],
    },
    'person_create': {
        'title': 'Create Person',
        'icon': 'bi-person-plus',
        'parent': ('Entities', 'entity_list'),
        'related': [],
    },
    'person_edit': {
        'title': 'Edit Person',
        'icon': 'bi-pencil-square',
        'parent': ('Entities', 'entity_list'),
        'related': [],
    },

    # Operation views
    'operation_list_view': {
        'title': 'Operations',
        'icon': 'bi-clock-history',
        'parent': ('Entities', 'entity_list'),
        'related': [
            ('Entity', 'entity_detail', {'pk': 'person_pk'}),
            ('Periods', 'period_list_view', {'entity_pk': 'person_pk'}),
            ('Create Operation', 'operation_create_view', {'pk': 'person_pk'}),
        ],
    },
    'operation_detail_view': {
        'title': 'Operation Detail',
        'icon': 'bi-receipt',
        'parent': ('Operations', 'operation_list_view', {'person_pk': 'source_pk'}),
        'related': [
            ('Edit', 'operation_update_view', {'pk': 'pk'}),
            ('Reverse', 'operation_reverse_view', {'pk': 'pk'}),
        ],
    },
    'operation_update_view': {
        'title': 'Edit Operation',
        'icon': 'bi-pencil-square',
        'parent': ('Operations', 'operation_list_view', {'person_pk': 'source_pk'}),
        'related': [
            ('Detail', 'operation_detail_view', {'pk': 'pk'}),
        ],
    },
    'operation_reverse_view': {
        'title': 'Reverse Operation',
        'icon': 'bi-arrow-counterclockwise',
        'parent': ('Operations', 'operation_list_view', {'person_pk': 'source_pk'}),
        'related': [],
    },
    'operation_create_view': {
        'title': 'Create Operation',
        'icon': 'bi-plus-circle',
        'parent': ('Operations', 'operation_list_view', {'person_pk': 'pk'}),
        'related': [],
    },

    # Period views
    'period_list_view': {
        'title': 'Periods',
        'icon': 'bi-calendar-month',
        'parent': ('Entities', 'entity_list'),
        'related': [
            ('Entity', 'entity_detail', {'pk': 'entity_pk'}),
            ('Operations', 'operation_list_view', {'person_pk': 'entity_pk'}),
            ('Create Period', 'period_create_view', {'entity_pk': 'entity_pk'}),
        ],
    },
    'period_detail_view': {
        'title': 'Period Detail',
        'icon': 'bi-calendar-check',
        'parent': ('Periods', 'period_list_view', {'entity_pk': 'entity_pk'}),
        'related': [
            ('Close Period', 'period_close_view', {'period_pk': 'pk'}),
        ],
    },
    'period_create_view': {
        'title': 'Create Period',
        'icon': 'bi-plus-circle',
        'parent': ('Periods', 'period_list_view', {'entity_pk': 'entity_pk'}),
        'related': [],
    },
    'period_close_view': {
        'title': 'Close Period',
        'icon': 'bi-lock',
        'parent': ('Periods', 'period_list_view', {'entity_pk': 'entity_pk'}),
        'related': [],
    },

    # Evaluation views
    'evaluation_create_view': {
        'title': 'Create Evaluation',
        'icon': 'bi-graph-up',
        'parent': ('Entities', 'entity_list'),
        'related': [],
    },

    # Purchase/Sale wizard views
    'purchase_wizard_step1': {
        'title': 'Purchase Wizard',
        'icon': 'bi-bag-check',
        'parent': ('Operations', 'operation_list_view', {'person_pk': 'pk'}),
        'related': [],
    },
    'purchase_invoice': {
        'title': 'Purchase Invoice',
        'icon': 'bi-receipt',
        'parent': ('Operations', 'operation_list_view', {'person_pk': 'pk'}),
        'related': [],
    },
    'sale_wizard_step1': {
        'title': 'Sale Wizard',
        'icon': 'bi-bag-check',
        'parent': ('Operations', 'operation_list_view', {'person_pk': 'pk'}),
        'related': [],
    },
    'sale_invoice': {
        'title': 'Sale Invoice',
        'icon': 'bi-receipt',
        'parent': ('Operations', 'operation_list_view', {'person_pk': 'pk'}),
        'related': [],
    },
}


def get_navigation_context(current_view_name, view_kwargs, entity=None, person_pk=None, period_pk=None):
    """
    Generate navigation context for the current view.

    Args:
        current_view_name: Name of the current URL pattern (e.g., 'entity_detail')
        view_kwargs: Dict of URL kwargs from the current view (e.g., {'pk': 123})
        entity: Optional Entity object for context
        person_pk: Optional person/entity PK
        period_pk: Optional period PK

    Returns:
        Dict with navigation structure for template rendering
    """
    nav_config = NAVIGATION_MAP.get(current_view_name, {})

    if not nav_config:
        return {
            'current_view': current_view_name,
            'show_navigation': False,
        }

    context = {
        'current_view': current_view_name,
        'show_navigation': True,
        'title': nav_config.get('title', ''),
        'icon': nav_config.get('icon', ''),
        'parent': None,
        'related_views': [],
    }

    # Build parent navigation
    if 'parent' in nav_config:
        parent_title, parent_view, param_map = nav_config['parent'] if len(nav_config['parent']) == 3 else (nav_config['parent'][0], nav_config['parent'][1], {})
        parent_kwargs = _map_params(param_map, view_kwargs)
        try:
            parent_url = reverse(parent_view, kwargs=parent_kwargs)
            context['parent'] = {
                'title': parent_title,
                'url': parent_url,
            }
        except Exception:
            context['parent'] = None

    # Build related views
    for rel_title, rel_view, param_map in nav_config.get('related', []):
        rel_kwargs = _map_params(param_map, view_kwargs)
        if rel_kwargs or not param_map:  # Include if we have kwargs or no mapping needed
            try:
                rel_url = reverse(rel_view, kwargs=rel_kwargs)
                context['related_views'].append({
                    'title': rel_title,
                    'url': rel_url,
                })
            except Exception:
                pass

    return context


def _map_params(param_map, view_kwargs):
    """
    Map view_kwargs to URL kwargs based on param_map.

    param_map: {'new_param': 'old_param'} means view_kwargs['old_param'] -> kwargs['new_param']
    """
    if not param_map:
        return {}

    mapped = {}
    for target_param, source_param in param_map.items():
        if source_param in view_kwargs:
            mapped[target_param] = view_kwargs[source_param]

    return mapped
