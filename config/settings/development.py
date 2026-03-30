from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

INSTALLED_APPS += ["django_browser_reload"]  # noqa: F405

MIDDLEWARE += ["django_browser_reload.middleware.BrowserReloadMiddleware"]  # noqa: F405

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
