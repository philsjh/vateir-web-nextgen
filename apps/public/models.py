from django.db import models


class Airport(models.Model):
    """An airport tracked by the vACC for briefing pages."""
    icao = models.CharField(max_length=4, unique=True)
    name = models.CharField(max_length=200, help_text="e.g. Dublin Airport")
    latitude = models.FloatField(default=0)
    longitude = models.FloatField(default=0)
    elevation_ft = models.IntegerField(default=0)
    description = models.TextField(blank=True, help_text="Briefing notes, procedures, etc.")
    # Chart links
    chart_ad_url = models.URLField(blank=True, help_text="Aerodrome chart URL")
    chart_sid_url = models.URLField(blank=True, help_text="SID chart URL")
    chart_star_url = models.URLField(blank=True, help_text="STAR chart URL")
    chart_iap_url = models.URLField(blank=True, help_text="Instrument approach chart URL")
    chart_ground_url = models.URLField(blank=True, help_text="Ground movement chart URL")
    chart_extra_urls = models.TextField(
        blank=True,
        help_text="Additional chart links, one per line in format: Label|URL",
    )

    staff_notice = models.TextField(
        blank=True,
        help_text="Staff notice/warning displayed at the top of the briefing page",
    )

    is_visible = models.BooleanField(default=True, help_text="Show on the airports page")
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "icao"]
        verbose_name = "Airport"
        verbose_name_plural = "Airports"

    def __str__(self):
        return f"{self.icao} — {self.name}"

    @property
    def extra_charts(self):
        """Parse chart_extra_urls into list of (label, url) tuples."""
        charts = []
        for line in self.chart_extra_urls.strip().splitlines():
            line = line.strip()
            if "|" in line:
                label, url = line.split("|", 1)
                charts.append((label.strip(), url.strip()))
        return charts


class Runway(models.Model):
    """A runway at an airport, used for preferential runway determination."""
    airport = models.ForeignKey(Airport, on_delete=models.CASCADE, related_name="runways")
    designator = models.CharField(max_length=3, help_text="e.g. 28L, 10R, 16")
    heading = models.PositiveSmallIntegerField(help_text="Magnetic heading in degrees (0-360)")
    length_m = models.PositiveIntegerField(default=0, help_text="Length in metres")
    preferential_arrival = models.BooleanField(
        default=False,
        help_text="Preferred for arrivals when tailwind is within threshold",
    )
    preferential_departure = models.BooleanField(
        default=False,
        help_text="Preferred for departures when tailwind is within threshold",
    )
    max_tailwind_kt = models.PositiveSmallIntegerField(
        default=5,
        help_text="Maximum tailwind component (knots) before switching off this runway",
    )

    class Meta:
        ordering = ["designator"]
        unique_together = ("airport", "designator")
        verbose_name = "Runway"
        verbose_name_plural = "Runways"

    def __str__(self):
        return f"{self.airport.icao} RWY {self.designator}"

    @property
    def length_ft(self):
        return round(self.length_m * 3.28084)


class NOTAM(models.Model):
    """Cached NOTAM from the external API."""
    notam_id = models.IntegerField(unique=True, help_text="CADS NOTAM ID")
    notam_number = models.CharField(max_length=30, blank=True)
    icao_location = models.CharField(max_length=50, db_index=True)
    status = models.CharField(max_length=20, help_text="NEW, REPLACE, or CANCELLED")
    raw_text = models.TextField(blank=True)
    icao_text = models.TextField(blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    radius_nm = models.FloatField(null=True, blank=True)
    begin_position = models.DateTimeField(null=True, blank=True)
    end_position = models.DateTimeField(null=True, blank=True)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-begin_position"]
        verbose_name = "NOTAM"
        verbose_name_plural = "NOTAMs"

    def __str__(self):
        return f"{self.notam_number} ({self.icao_location})"

    @property
    def is_active(self):
        return self.status in ("NEW", "REPLACE")


class StaffMember(models.Model):
    user = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        help_text="Link to VATSIM account (optional)",
    )
    name = models.CharField(max_length=200)
    position_title = models.CharField(
        max_length=200, help_text="e.g. 'vACC Director', 'Training Director'"
    )
    bio = models.TextField(blank=True)
    avatar_url = models.URLField(blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "Staff Member"
        verbose_name_plural = "Staff Members"

    def __str__(self):
        return f"{self.name} — {self.position_title}"


class InfoPage(models.Model):
    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=200)
    content = models.TextField(help_text="HTML content for the page")
    is_published = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "title"]
        verbose_name = "Info Page"
        verbose_name_plural = "Info Pages"

    def __str__(self):
        return self.title


class DocumentCategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "Document Category"
        verbose_name_plural = "Document Categories"

    def __str__(self):
        return self.name


class AccessLevel(models.TextChoices):
    PUBLIC = "PUBLIC", "Public"
    AUTHENTICATED = "AUTHENTICATED", "Authenticated Users"
    APPROVED_CONTROLLERS = "APPROVED_CONTROLLERS", "Approved Controllers Only"


class Document(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        DocumentCategory, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="documents",
    )
    file = models.FileField(upload_to="documents/")
    file_size = models.PositiveIntegerField(default=0, help_text="Size in bytes")
    is_published = models.BooleanField(default=True)
    access_level = models.CharField(
        max_length=25, choices=AccessLevel.choices, default=AccessLevel.PUBLIC,
        help_text="Who can view this document",
    )
    uploaded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Document"
        verbose_name_plural = "Documents"

    def __str__(self):
        return self.title

    @property
    def file_size_display(self):
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.0f} KB"
        else:
            return f"{self.file_size / (1024 * 1024):.1f} MB"

    @property
    def file_extension(self):
        if self.file and self.file.name:
            return self.file.name.rsplit(".", 1)[-1].upper() if "." in self.file.name else ""
        return ""
