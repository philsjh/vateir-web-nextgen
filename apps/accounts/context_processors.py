import logging

from django.core.cache import cache

from .models import RoleType

logger = logging.getLogger(__name__)


def user_roles(request):
    """Inject role flags and site config into every template context."""
    ctx = {
        "is_staff_member": False,
        "is_admin": False,
        "is_superadmin": False,
        "is_mentor": False,
        "is_examiner": False,
        "site_config": None,
    }
    try:
        if hasattr(request, "user") and request.user.is_authenticated:
            roles = set(request.user.roles.values_list("role", flat=True))
            is_superadmin = request.user.is_superuser or RoleType.SUPERADMIN in roles
            is_admin = is_superadmin or RoleType.ADMIN in roles
            is_staff = is_admin or RoleType.STAFF in roles
            ctx["is_superadmin"] = is_superadmin
            ctx["is_admin"] = is_admin
            ctx["is_staff_member"] = is_staff
            ctx["is_mentor"] = is_staff or RoleType.MENTOR in roles
            ctx["is_examiner"] = is_staff or RoleType.EXAMINER in roles
    except Exception as e:
        logger.debug("user_roles: error checking roles: %s", e)

    # Site config (cached for 60s)
    try:
        site_config = cache.get("site_config")
        if site_config is None:
            from .models import SiteConfig
            site_config = SiteConfig.get()
            cache.set("site_config", site_config, 60)
        ctx["site_config"] = site_config
    except Exception as e:
        logger.debug("user_roles: error loading site config: %s", e)

    try:
        from django.conf import settings
        ctx["logo_filename"] = settings.SITE_LOGO_FILENAME
    except AttributeError:
        ctx["logo_filename"] = "logo.png"

    return ctx
