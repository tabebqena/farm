from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Get item from dict or list by key."""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    try:
        return dictionary[int(key) if isinstance(key, str) and key.isdigit() else key]
    except (KeyError, TypeError, IndexError, ValueError):
        return None


@register.filter
def add(value, arg):
    """Add two values."""
    try:
        return int(value) + int(arg)
    except (ValueError, TypeError):
        return value
