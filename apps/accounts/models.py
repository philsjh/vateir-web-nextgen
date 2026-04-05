from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class NameDisplay(models.TextChoices):
    HIDDEN = "HIDDEN", "Hidden (show CID only)"
    FIRST_NAME = "FIRST_NAME", "First name only"
    INITIALS = "INITIALS", "Initials only"
    FULL_NAME = "FULL_NAME", "Full name"


class User(AbstractUser):
    """
    Custom user model where authentication is done exclusively via VATSIM
    Connect OAuth2. The 'username' field stores the CID as a string for
    compatibility; `cid` is the canonical integer identifier.
    """

    cid = models.PositiveIntegerField(
        unique=True, null=True, blank=True, help_text="VATSIM Certificate ID"
    )
    vatsim_name = models.CharField(
        max_length=255, blank=True, help_text="Full name as returned by VATSIM OAuth2"
    )
    name_display = models.CharField(
        max_length=20,
        choices=NameDisplay.choices,
        default=NameDisplay.FULL_NAME,
        help_text="How this user's name appears to authenticated visitors",
    )
    email = models.EmailField(blank=True)
    rating = models.PositiveSmallIntegerField(
        default=1, help_text="VATSIM rating integer (1=OBS ... 12=ADM)"
    )
    discord_user_id = models.CharField(
        max_length=20, blank=True, default="",
        help_text="Discord user snowflake ID",
    )

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return f"{self.vatsim_name or self.username} (CID {self.cid})"

    @property
    def initials(self) -> str:
        parts = self.vatsim_name.split() if self.vatsim_name else []
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        if parts:
            return parts[0][0].upper()
        return str(self.cid or "?")[0]

    @property
    def rating_label(self):
        return settings.VATSIM_RATINGS.get(self.rating, str(self.rating))

    def get_display_name(self, viewer_is_authenticated: bool = False) -> str:
        if not viewer_is_authenticated or self.name_display == NameDisplay.HIDDEN:
            return str(self.cid) if self.cid else self.username

        parts = self.vatsim_name.split() if self.vatsim_name else []

        if self.name_display == NameDisplay.FIRST_NAME:
            return parts[0] if parts else str(self.cid)

        if self.name_display == NameDisplay.INITIALS:
            return (
                " ".join(p[0].upper() + "." for p in parts) if parts else str(self.cid)
            )

        return self.vatsim_name or str(self.cid)


class RoleType(models.TextChoices):
    SUPERADMIN = "SUPERADMIN", "Super Admin"
    ADMIN = "ADMIN", "Admin"
    STAFF = "STAFF", "Staff"
    MENTOR = "MENTOR", "Mentor"
    EXAMINER = "EXAMINER", "Examiner"


class Role(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="roles")
    role = models.CharField(max_length=20, choices=RoleType.choices)
    granted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_roles",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "role")
        verbose_name = "Role"
        verbose_name_plural = "Roles"

    def __str__(self):
        return f"{self.user} — {self.role}"


class SiteConfig(models.Model):
    """Singleton model for site-wide configuration."""

    # Branding
    site_name = models.CharField(
        max_length=100, default=settings.DEFAULT_SITE_NAME,
        help_text="Displayed in the browser title bar and login page",
    )
    topbar_text = models.CharField(
        max_length=100, default=settings.DEFAULT_TOPBAR_TEXT,
        help_text="Text displayed in the top navigation bar",
    )
    fir_name = models.CharField(
        max_length=100, default=settings.DEFAULT_FIR_NAME,
        help_text="FIR name for display (e.g. 'Shannon/Dublin FIR')",
    )
    fir_long_name = models.CharField(
        max_length=200, default=settings.DEFAULT_FIR_LONG_NAME,
        help_text="Full FIR name with location",
    )

    # Callsign filtering
    callsign_prefixes = models.CharField(
        max_length=200, default=settings.DEFAULT_CALLSIGN_PREFIXES,
        help_text="Comma-separated callsign prefixes to track (e.g. 'EI')",
    )

    # METAR configuration
    metar_icaos = models.CharField(
        max_length=200, default=settings.DEFAULT_METAR_ICAOS,
        help_text="Comma-separated ICAO codes for METAR display (e.g. 'EIDW,EINN,EICK')",
    )

    # Features
    enable_metar_widget = models.BooleanField(default=True)
    enable_events_page = models.BooleanField(default=True)
    enable_feedback_page = models.BooleanField(default=True)

    # Theme customisation
    primary_color_from = models.CharField(
        max_length=7, default="#059669",
        help_text="Gradient start colour (hex)",
    )
    primary_color_to = models.CharField(
        max_length=7, default="#10b981",
        help_text="Gradient end colour (hex)",
    )

    # Homepage content
    hero_title = models.CharField(
        max_length=200, default="Welcome to VATéir",
        help_text="Main hero heading on the homepage",
    )
    hero_subtitle = models.TextField(
        default="Virtual Air Traffic Control for Ireland — Shannon and Dublin FIR",
        help_text="Subtitle text below the hero heading",
    )

    # Discord integration
    discord_webhook_url = models.URLField(
        blank=True, help_text="Legacy webhook URL (use bot channels below instead)"
    )
    discord_guild_id = models.CharField(
        max_length=20, blank=True, help_text="Discord server/guild ID"
    )
    discord_roster_channel_id = models.CharField(
        max_length=20, blank=True, help_text="Channel for roster sync notifications"
    )
    discord_training_channel_id = models.CharField(
        max_length=20, blank=True, help_text="Channel for training notifications"
    )
    discord_events_channel_id = models.CharField(
        max_length=20, blank=True, help_text="Channel for event notifications"
    )
    discord_general_channel_id = models.CharField(
        max_length=20, blank=True, help_text="Channel for general notifications"
    )
    discord_tickets_channel_id = models.CharField(
        max_length=20, blank=True, help_text="Channel for support ticket notifications"
    )

    # Support tickets
    ticket_sla_hours = models.PositiveIntegerField(
        default=48, help_text="Hours before a ticket is considered SLA-breached"
    )
    enable_tickets = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Site Configuration"
        verbose_name_plural = "Site Configuration"

    def __str__(self):
        return "Site Configuration"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        from django.core.cache import cache
        cache.delete("site_config")

    @classmethod
    def get(cls):
        """Return the singleton config, creating it if needed."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def get_callsign_prefixes(self):
        return [p.strip().upper() for p in self.callsign_prefixes.split(",") if p.strip()]

    def get_metar_icaos(self):
        return [i.strip().upper() for i in self.metar_icaos.split(",") if i.strip()]

    def get_callsign_regex(self):
        import re
        prefixes = self.get_callsign_prefixes()
        if not prefixes:
            return re.compile(r"^$")
        parts = [f"^{re.escape(p)}[A-Z0-9_]*" for p in prefixes]
        return re.compile("|".join(parts), re.IGNORECASE)
