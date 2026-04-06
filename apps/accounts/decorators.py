"""
RBAC decorators for VATéir.
"""

import functools
from django.shortcuts import redirect


def permission_required(codename):
    """
    Decorator that checks if the user has a specific permission.
    Works via role profiles and direct user permission grants.
    Superusers bypass all checks.
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("accounts:login")
            if request.user.has_permission(codename):
                return view_func(request, *args, **kwargs)
            return redirect("dashboard:index")
        return wrapped
    return decorator
