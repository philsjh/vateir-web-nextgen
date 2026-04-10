from django.conf import settings
from django.db import models


# ─── Position colour assignments for roster display ───────────────
POSITION_COLORS = [
    ("#059669", "#d1fae5"),  # emerald
    ("#2563eb", "#dbeafe"),  # blue
    ("#d97706", "#fef3c7"),  # amber
    ("#7c3aed", "#ede9fe"),  # violet
    ("#dc2626", "#fee2e2"),  # red
    ("#0891b2", "#cffafe"),  # cyan
    ("#c026d3", "#fae8ff"),  # fuchsia
    ("#65a30d", "#ecfccb"),  # lime
]


class Event(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    banner_image = models.ImageField(upload_to="events/banners/", blank=True, null=True)
    banner_url = models.URLField(blank=True, help_text="Fallback external banner URL")
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    is_published = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)
    roster_published = models.BooleanField(
        default=False, help_text="When true, the roster is visible to logged-in controllers"
    )
    roster_public = models.BooleanField(
        default=False, help_text="When true, the roster is also visible on the public event page"
    )
    airport = models.ForeignKey(
        "public.Airport", on_delete=models.SET_NULL, null=True, blank=True,
        help_text="Primary airport for this event",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_datetime"]
        verbose_name = "Event"
        verbose_name_plural = "Events"

    def __str__(self):
        return self.title

    @property
    def banner_display_url(self):
        if self.banner_image:
            return self.banner_image.url
        return self.banner_url or ""

    def get_roster_groups(self):
        """Group roster positions by airport/type with color assignments."""
        positions = self.positions.select_related(
            "position__airport", "assigned_controller"
        ).order_by("position__airport__icao", "position__position_type", "position__callsign")

        groups = {}
        for ep in positions:
            key = ep.position.airport.icao if ep.position.airport else (ep.position.position_type or "Other")
            if key not in groups:
                groups[key] = []
            groups[key].append(ep)

        # Assign colors to groups
        result = []
        for idx, (group_name, eps) in enumerate(groups.items()):
            color_bg, color_text_bg = POSITION_COLORS[idx % len(POSITION_COLORS)]
            result.append({
                "name": group_name,
                "color_bg": color_bg,
                "color_light": color_text_bg,
                "positions": eps,
            })
        return result


class EventPosition(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="positions")
    position = models.ForeignKey(
        "controllers.Position", on_delete=models.CASCADE
    )
    assigned_controller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="event_positions",
    )
    start_time = models.DateTimeField(
        null=True, blank=True,
        help_text="Slot start — defaults to event start if blank",
    )
    end_time = models.DateTimeField(
        null=True, blank=True,
        help_text="Slot end — defaults to event end if blank",
    )
    is_filled = models.BooleanField(default=False)

    class Meta:
        ordering = ["position__airport__icao", "position__callsign", "start_time"]
        verbose_name = "Event Position"
        verbose_name_plural = "Event Positions"

    def __str__(self):
        return f"{self.event.title} — {self.position.callsign}"

    @property
    def min_rating(self):
        return self.position.min_rating

    @property
    def rating_label(self):
        return self.position.rating_label

    @property
    def effective_start(self):
        return self.start_time or self.event.start_datetime

    @property
    def effective_end(self):
        return self.end_time or self.event.end_datetime


class EventAvailability(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="availability")
    controller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_availability"
    )
    preferred_positions = models.ManyToManyField(
        "controllers.Position", blank=True
    )
    available_from = models.DateTimeField(
        null=True, blank=True,
        help_text="When the controller is available from",
    )
    available_to = models.DateTimeField(
        null=True, blank=True,
        help_text="When the controller is available until",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("event", "controller")
        verbose_name = "Event Availability"
        verbose_name_plural = "Event Availability"

    def __str__(self):
        return f"{self.controller} available for {self.event.title}"
