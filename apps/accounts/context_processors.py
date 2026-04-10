import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)


def user_roles(request):
    """Inject permission-derived role flags and site config into every template context."""
    ctx = {
        "is_staff_member": False,
        "is_admin": False,
        "is_superadmin": False,
        "is_mentor": False,
        "is_examiner": False,
        "has_active_training": False,
        "site_config": None,
    }
    try:
        if hasattr(request, "user") and request.user.is_authenticated:
            has = request.user.has_permission
            is_superadmin = request.user.is_superuser
            ctx["is_superadmin"] = is_superadmin
            ctx["is_admin"] = is_superadmin or has("admin_panel.site_config")
            ctx["is_staff_member"] = ctx["is_admin"] or has("admin_panel.access")
            ctx["is_mentor"] = ctx["is_staff_member"] or has("training.mentor")
            ctx["is_examiner"] = ctx["is_staff_member"] or has("training.examine")

            from apps.training.models import TrainingRequest
            ctx["has_active_training"] = TrainingRequest.objects.filter(
                student=request.user,
                status__in=["ACCEPTED", "IN_PROGRESS"],
            ).exists()
    except Exception as e:
        logger.debug("user_roles: error checking roles: %s", e)

    # Site config (cached for 60s)
    try:
        site_config = cache.get("site_config")
        if site_config is None:
            from apps.accounts.models import SiteConfig
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
