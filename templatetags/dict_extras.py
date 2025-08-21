from django import template

register = template.Library()

@register.filter
def get_item(d, key):
    """
    Umożliwia użycie: {{ some_dict|get_item:dynamic_key }}
    Zwraca "" gdy klucza brak lub d nie jest dict-em.
    """
    if isinstance(d, dict):
        return d.get(key, "")
    return ""
