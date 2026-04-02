from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("django-admin/", admin.site.urls),

    # Authentication
    path("auth/", include("apps.accounts.urls", namespace="accounts")),
    path("", include("social_django.urls", namespace="social")),

    # Public pages
    path("", include("apps.public.urls", namespace="public")),

    # Authenticated dashboard
    path("dashboard/", include("apps.dashboard.urls", namespace="dashboard")),

    # Controllers (public roster + detail)
    path("controllers/", include("apps.controllers.urls", namespace="controllers")),

    # Training (authenticated)
    path("training/", include("apps.training.urls", namespace="training")),

    # Events (public listing + authenticated availability)
    path("events/", include("apps.events.urls", namespace="events")),

    # Feedback (public submission + staff review)
    path("feedback/", include("apps.feedback.urls", namespace="feedback")),

    # Admin panel (staff only)
    path("admin-panel/", include("apps.admin_panel.urls", namespace="admin_panel")),
]

if settings.DEBUG:
    from django.conf.urls.static import static
    urlpatterns += [
        path("__reload__/", include("django_browser_reload.urls")),
    ]
    if not settings.DO_SPACES_KEY:
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
