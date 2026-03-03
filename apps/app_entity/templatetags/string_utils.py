from django import template

register = template.Library()


@register.filter(name="split")
def split(value, key):
    """
    Returns the value split by the key.
    Usage: {{ "Label: Error"|split:":" }}
    """
    return value.split(key)


@register.filter(name="split_filter")
def split_filter(value, key):
    """
    Returns the value split by the key.
    Usage: {{ "Label: Error"|split:":" }}
    """
    return value.split(key)


@register.filter(name="trim")
def trim(value: str):
    return value.strip()
