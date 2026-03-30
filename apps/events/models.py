from django.conf import settings
from django.db import models


class Event(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    banner_image = models.ImageField(upload_to="events/banners/", blank=True, null=True)
    banner_url = models.URLField(blank=True, help_text="External banner image URL")
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    is_published = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)
    airport_icao = models.CharField(max_length=4, blank=True)
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


class EventPosition(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="positions")
    position = models.ForeignKey(
        "controllers.Position", on_delete=models.CASCADE
    )
    min_rating = models.PositiveSmallIntegerField(
        default=1, help_text="Minimum VATSIM rating to hold this position"
    )
    assigned_controller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="event_positions",
    )
    is_filled = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Event Position"
        verbose_name_plural = "Event Positions"

    def __str__(self):
        return f"{self.event.title} — {self.position.callsign}"


class EventAvailability(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="availability")
    controller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_availability"
    )
    preferred_positions = models.ManyToManyField(
        "controllers.Position", blank=True
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("event", "controller")
        verbose_name = "Event Availability"
        verbose_name_plural = "Event Availability"

    def __str__(self):
        return f"{self.controller} available for {self.event.title}"
