"""
timetable/templatetags/timetable_tags.py

Custom template filters for timetable grid rendering.
"""

from django import template

register = template.Library()


@register.filter
def lookup(dictionary, key):
    """
    Look up a key in a dict.  Usage:  {{ mydict|lookup:key }}

    Returns None (renders as '') if the key doesn't exist or the
    value is not a dict.
    """
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None
