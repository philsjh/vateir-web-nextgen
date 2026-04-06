from django import template

register = template.Library()


@register.filter
def has_vateir_perm(user, codename):
    """Check if a user has a specific VATéir permission."""
    if not user or not user.is_authenticated:
        return False
    return user.has_permission(codename)
