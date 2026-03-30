"""
RBAC decorators for VATéir.
"""

import functools
from django.shortcuts import redirect
from .models import RoleType


def rbac_required(minimum_role: str):
    """
    Decorator that checks the user has at least the given role.
    Role hierarchy (most to least privilege): SUPERADMIN > ADMIN > STAFF > MENTOR/EXAMINER.
    """
    hierarchy = [RoleType.STAFF, RoleType.ADMIN, RoleType.SUPERADMIN]

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("accounts:login")
            user_roles = set(request.user.roles.values_list("role", flat=True))
            required_index = hierarchy.index(minimum_role)
            if any(
                hierarchy.index(r) >= required_index
                for r in user_roles
                if r in hierarchy
            ):
                return view_func(request, *args, **kwargs)
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            return redirect("dashboard:index")

        return wrapped

    return decorator


def mentor_required(view_func):
    """Require MENTOR, EXAMINER, STAFF, ADMIN, or SUPERADMIN role."""
    @functools.wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        user_roles = set(request.user.roles.values_list("role", flat=True))
        allowed = {RoleType.MENTOR, RoleType.EXAMINER, RoleType.STAFF, RoleType.ADMIN, RoleType.SUPERADMIN}
        if user_roles & allowed or request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        return redirect("dashboard:index")
    return wrapped
