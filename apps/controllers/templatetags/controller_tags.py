from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def controller_name(context, controller):
    """
    Return the controller's display name respecting privacy settings.
    Uses the linked User's name_display preference if they have one.
    """
    request = context.get("request")
    viewer_authed = request.user.is_authenticated if request else False
    return controller.get_display_name(viewer_is_authenticated=viewer_authed)


@register.filter
def dict_lookup(dictionary, key):
    """Look up a key in a dictionary. Usage: {{ mydict|dict_lookup:key }}"""
    if isinstance(dictionary, dict):
        return dictionary.get(key, [])
    return []


@register.simple_tag(takes_context=True)
def user_display_name(context, user_obj):
    """
    Return a User's display name respecting their privacy settings.
    """
    request = context.get("request")
    viewer_authed = request.user.is_authenticated if request else False
    if hasattr(user_obj, "get_display_name"):
        return user_obj.get_display_name(viewer_is_authenticated=viewer_authed)
    return str(user_obj)
