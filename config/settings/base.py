"""
Base Django settings for VATéir Control Centre.
"""

from pathlib import Path
import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

# Application definition
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS = [
    "tailwind",
    "theme",
    "social_django",
    "django_celery_beat",
    "django_celery_results",
    "storages",
    "widget_tweaks",
    "django_htmx",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.controllers",
    "apps.public",
    "apps.dashboard",
    "apps.training",
    "apps.events",
    "apps.feedback",
    "apps.admin_panel",
    "apps.notifications",
    "apps.tickets",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "social_django.middleware.SocialAuthExceptionMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "social_django.context_processors.backends",
                "social_django.context_processors.login_redirect",
                "apps.accounts.context_processors.user_roles",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database
DATABASES = {
    "default": env.db("DATABASE_URL", default="postgres://localhost/vateir")
}

# Cache (Redis)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://127.0.0.1:6379/0"),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalisation
LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom user model
AUTH_USER_MODEL = "accounts.User"

# Authentication backends
AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.VATSIMOAuth2",
    "django.contrib.auth.backends.ModelBackend",
]

# Social Auth (VATSIM Connect)
SOCIAL_AUTH_VATSIM_KEY = env("VATSIM_CLIENT_ID", default="")
SOCIAL_AUTH_VATSIM_SECRET = env("VATSIM_CLIENT_SECRET", default="")
SOCIAL_AUTH_VATSIM_SCOPE = ["full_name", "email", "vatsim_details", "country"]

SOCIAL_AUTH_PIPELINE = [
    "social_core.pipeline.social_auth.social_details",
    "social_core.pipeline.social_auth.social_uid",
    "social_core.pipeline.social_auth.auth_allowed",
    "social_core.pipeline.social_auth.social_user",
    "social_core.pipeline.user.get_username",
    "social_core.pipeline.social_auth.associate_by_email",
    "apps.accounts.pipeline.get_or_create_user",
    "social_core.pipeline.social_auth.associate_user",
    "social_core.pipeline.social_auth.load_extra_data",
    "social_core.pipeline.user.user_details",
    "apps.accounts.pipeline.update_user_details",
]

SOCIAL_AUTH_LOGIN_REDIRECT_URL = "/dashboard/"
SOCIAL_AUTH_LOGIN_ERROR_URL = "/auth/login/"
SOCIAL_AUTH_NEW_USER_REDIRECT_URL = "/auth/settings/"

LOGIN_URL = "/auth/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/"

# Tailwind
TAILWIND_APP_NAME = "theme"
INTERNAL_IPS = ["127.0.0.1"]

# Celery
CELERY_BROKER_URL = env("REDIS_URL", default="redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = "django-db"
CELERY_CACHE_BACKEND = "django-cache"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_RESULT_EXTENDED = True

# VATSIM API settings
VATSIM_API_BASE = env("VATSIM_API_BASE", default="https://api.vatsim.net/v2")
VATSIM_API_KEY = env("VATSIM_API_KEY", default="")
VATSIM_DATA_FEED = env("VATSIM_DATA_FEED", default="https://data.vatsim.net/v3/vatsim-data.json")
VATSIM_SUBDIVISION = env("VATSIM_SUBDIVISION", default="IRL")
BACKFILL_YEARS = env.int("BACKFILL_YEARS", default=0)

# METAR airports
DEFAULT_METAR_ICAOS = env("FIR_METAR_ICAOS", default="EIDW,EINN,EICK")

# Rating map
VATSIM_RATINGS = {
    -1: "INA",
    0: "SUS",
    1: "OBS",
    2: "S1",
    3: "S2",
    4: "S3",
    5: "C1",
    7: "C3",
    8: "I1",
    10: "I3",
    11: "SUP",
    12: "ADM",
}

# FIR Configuration (used as defaults for SiteConfig model)
DEFAULT_SITE_NAME = env("FIR_SITE_NAME", default="VATéir Control Centre")
DEFAULT_TOPBAR_TEXT = env("FIR_TOPBAR_TEXT", default="VATéir")
DEFAULT_FIR_NAME = env("FIR_NAME", default="Shannon/Dublin FIR")
DEFAULT_FIR_LONG_NAME = env("FIR_LONG_NAME", default="Shannon and Dublin FIR (Ireland)")
DEFAULT_CALLSIGN_PREFIXES = env("FIR_CALLSIGN_PREFIXES", default="EI")

# Site Branding
DISCORD_BOT_TOKEN = env("DISCORD_BOT_TOKEN", default="")

SITE_LOGO_FILENAME = env("SITE_LOGO_FILENAME", default="logo.png")
APP_NAME = env("APP_NAME", default="vateir")
APP_USER = env("APP_USER", default="vateir")

# DigitalOcean Spaces / S3 Storage
DO_SPACES_KEY = env("DO_SPACES_KEY", default="")
DO_SPACES_SECRET = env("DO_SPACES_SECRET", default="")
DO_SPACES_BUCKET = env("DO_SPACES_BUCKET", default="vateir")
DO_SPACES_REGION = env("DO_SPACES_REGION", default="fra1")
DO_SPACES_ENDPOINT = env("DO_SPACES_ENDPOINT", default=f"https://{DO_SPACES_REGION}.digitaloceanspaces.com")
DO_SPACES_CDN_DOMAIN = env("DO_SPACES_CDN_DOMAIN", default="")

if DO_SPACES_KEY:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
    }
    AWS_ACCESS_KEY_ID = DO_SPACES_KEY
    AWS_SECRET_ACCESS_KEY = DO_SPACES_SECRET
    AWS_STORAGE_BUCKET_NAME = DO_SPACES_BUCKET
    AWS_S3_REGION_NAME = DO_SPACES_REGION
    AWS_S3_ENDPOINT_URL = DO_SPACES_ENDPOINT
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
    AWS_DEFAULT_ACL = "public-read"
    AWS_QUERYSTRING_AUTH = False
    AWS_LOCATION = "media"
    if DO_SPACES_CDN_DOMAIN:
        AWS_S3_CUSTOM_DOMAIN = DO_SPACES_CDN_DOMAIN
    else:
        AWS_S3_CUSTOM_DOMAIN = f"{DO_SPACES_BUCKET}.{DO_SPACES_REGION}.cdn.digitaloceanspaces.com"
    MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_LOCATION}/"
else:
    # Local media fallback for development
    MEDIA_URL = "/media/"
    MEDIA_ROOT = BASE_DIR / "media"
