import secrets
import hashlib

from django.conf import settings
from django.db import models
from django.utils import timezone


def generate_api_key():
    """Generate a secure random API key with a vateir_ prefix."""
    return f"vateir_{secrets.token_hex(32)}"


def hash_key(raw_key: str) -> str:
    """SHA-256 hash of the API key for secure storage."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


class APIKey(models.Model):
    """An API key for programmatic access."""
    name = models.CharField(max_length=100, help_text="Descriptive name for this key")
    prefix = models.CharField(
        max_length=12, db_index=True,
        help_text="First 12 chars of the key for identification",
    )
    key_hash = models.CharField(max_length=64, unique=True, help_text="SHA-256 hash of the full key")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="api_keys_created",
    )
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Leave blank for no expiry")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "API Key"
        verbose_name_plural = "API Keys"

    def __str__(self):
        return f"{self.name} ({self.prefix}...)"

    @property
    def is_expired(self):
        if self.expires_at and self.expires_at < timezone.now():
            return True
        return False

    @property
    def is_valid(self):
        return self.is_active and not self.is_expired

    def record_usage(self):
        APIKey.objects.filter(pk=self.pk).update(last_used_at=timezone.now())

    @classmethod
    def create_key(cls, name, created_by=None, expires_at=None):
        """Create a new API key. Returns (api_key_obj, raw_key)."""
        raw_key = generate_api_key()
        key = cls.objects.create(
            name=name,
            prefix=raw_key[:12],
            key_hash=hash_key(raw_key),
            created_by=created_by,
            expires_at=expires_at,
        )
        return key, raw_key

    @classmethod
    def authenticate(cls, raw_key: str):
        """Look up and validate an API key. Returns the APIKey or None."""
        if not raw_key:
            return None
        hashed = hash_key(raw_key)
        try:
            key = cls.objects.get(key_hash=hashed)
        except cls.DoesNotExist:
            return None
        if not key.is_valid:
            return None
        key.record_usage()
        return key


class CustomEndpoint(models.Model):
    """A custom API endpoint with a manually defined response."""
    CONTENT_TYPES = [
        ("application/json", "JSON"),
        ("text/plain", "Plain Text"),
        ("text/html", "HTML"),
        ("application/xml", "XML"),
        ("text/csv", "CSV"),
    ]

    path = models.CharField(
        max_length=500, unique=True,
        help_text="URL path after /api/custom/ — e.g. plugins/a/b/config",
    )
    name = models.CharField(max_length=200, help_text="Descriptive name")
    description = models.TextField(blank=True)
    content_type = models.CharField(
        max_length=50, choices=CONTENT_TYPES, default="application/json",
    )
    response_body = models.TextField(
        help_text="The response body. For JSON, must be valid JSON.",
    )
    status_code = models.PositiveSmallIntegerField(default=200)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["path"]
        verbose_name = "Custom Endpoint"
        verbose_name_plural = "Custom Endpoints"

    def __str__(self):
        return f"{self.path} ({self.name})"

    @property
    def full_path(self):
        return f"/api/custom/{self.path.lstrip('/')}"
