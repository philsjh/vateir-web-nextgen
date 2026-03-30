from django.conf import settings
from django.db import models


class BackfillStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    COMPLETE = "COMPLETE", "Complete"
    FAILED = "FAILED", "Failed"


class PositionType(models.TextChoices):
    DELIVERY = "DELIVERY", "Delivery"
    GROUND = "GROUND", "Ground"
    TOWER = "TOWER", "Tower"
    APPROACH = "APPROACH", "Approach"
    ACC = "ACC", "ACC"


class Position(models.Model):
    callsign = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100, blank=True, help_text="Friendly name, e.g. 'Dublin Tower'")
    position_type = models.CharField(
        max_length=10, choices=PositionType.choices, blank=True
    )
    airport_icao = models.CharField(
        max_length=4, blank=True, help_text="e.g. EIDW, EINN"
    )
    frequency = models.CharField(max_length=10, blank=True)
    is_home = models.BooleanField(
        default=False, db_index=True,
        help_text="Position belongs to the home FIR (EI*)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["callsign"]
        verbose_name = "Position"
        verbose_name_plural = "Positions"

    def __str__(self):
        if self.name:
            return f"{self.name} ({self.callsign})"
        return self.callsign


class Controller(models.Model):
    """A registered VATSIM controller tracked by VATéir."""

    cid = models.PositiveIntegerField(
        primary_key=True, help_text="VATSIM Certificate ID"
    )
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    rating = models.PositiveSmallIntegerField(
        default=1, help_text="VATSIM rating integer (1=OBS ... 12=ADM)"
    )
    is_active = models.BooleanField(default=True)
    is_home_controller = models.BooleanField(
        default=True, help_text="Belongs to VATéir (vs visitor)"
    )
    notes = models.TextField(blank=True)

    # Backfill tracking
    backfill_status = models.CharField(
        max_length=20, choices=BackfillStatus.choices, default=BackfillStatus.PENDING,
    )
    backfill_started_at = models.DateTimeField(null=True, blank=True)
    backfill_completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["cid"]
        verbose_name = "Controller"
        verbose_name_plural = "Controllers"

    def __str__(self):
        name = f"{self.first_name} {self.last_name}".strip() or "Unknown"
        return f"{name} ({self.cid})"

    @property
    def display_name(self):
        return f"{self.first_name} {self.last_name}".strip() or str(self.cid)

    @property
    def rating_label(self):
        return settings.VATSIM_RATINGS.get(self.rating, str(self.rating))


class ControllerStats(models.Model):
    """Cached lifetime stats from VATSIM API."""

    controller = models.OneToOneField(
        Controller, on_delete=models.CASCADE, related_name="stats", primary_key=True
    )

    atc = models.FloatField(default=0.0, help_text="Total ATC hours")
    pilot = models.FloatField(default=0.0, help_text="Total pilot hours")

    s1 = models.FloatField(default=0.0)
    s2 = models.FloatField(default=0.0)
    s3 = models.FloatField(default=0.0)
    c1 = models.FloatField(default=0.0)
    c2 = models.FloatField(default=0.0)
    c3 = models.FloatField(default=0.0)
    i1 = models.FloatField(default=0.0)
    i2 = models.FloatField(default=0.0)
    i3 = models.FloatField(default=0.0)
    sup = models.FloatField(default=0.0)
    adm = models.FloatField(default=0.0)

    last_updated = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Controller Stats"

    def __str__(self):
        return f"Stats for {self.controller}"

    @property
    def rating_hours(self):
        return [
            ("S1", self.s1), ("S2", self.s2), ("S3", self.s3),
            ("C1", self.c1), ("C2", self.c2), ("C3", self.c3),
            ("I1", self.i1), ("I2", self.i2), ("I3", self.i3),
            ("SUP", self.sup), ("ADM", self.adm),
        ]


class ATCSession(models.Model):
    """A completed VATSIM ATC session."""

    connection_id = models.BigIntegerField(unique=True, db_index=True)
    cid = models.PositiveIntegerField(db_index=True)
    controller = models.ForeignKey(
        Controller, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sessions",
    )
    callsign = models.CharField(max_length=20, db_index=True)
    position = models.ForeignKey(
        Position, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sessions",
    )
    rating = models.PositiveSmallIntegerField(default=1)
    start = models.DateTimeField(db_index=True)
    end = models.DateTimeField()
    duration_minutes = models.FloatField(default=0.0)
    server = models.CharField(max_length=50, blank=True)

    aircraft_tracked = models.PositiveIntegerField(default=0)
    aircraft_seen = models.PositiveIntegerField(default=0)
    flights_amended = models.PositiveIntegerField(default=0)
    handoffs_initiated = models.PositiveIntegerField(default=0)
    handoffs_received = models.PositiveIntegerField(default=0)
    handoffs_refused = models.PositiveIntegerField(default=0)
    squawks_assigned = models.PositiveIntegerField(default=0)
    cruise_alts_modified = models.PositiveIntegerField(default=0)
    temp_alts_modified = models.PositiveIntegerField(default=0)
    scratchpad_mods = models.PositiveIntegerField(default=0)

    is_backfilled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start"]
        verbose_name = "ATC Session"
        verbose_name_plural = "ATC Sessions"
        indexes = [
            models.Index(fields=["cid", "start"]),
            models.Index(fields=["callsign", "start"]),
        ]

    def __str__(self):
        return f"{self.callsign} | CID {self.cid} | {self.start:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        if self.start and self.end:
            delta = self.end - self.start
            self.duration_minutes = delta.total_seconds() / 60.0
        super().save(*args, **kwargs)

    @property
    def duration_hours(self):
        return round(self.duration_minutes / 60.0, 2)

    @property
    def rating_label(self):
        return settings.VATSIM_RATINGS.get(self.rating, str(self.rating))


class LiveSession(models.Model):
    """An in-progress VATSIM ATC session from the live data feed."""

    connection_id = models.BigIntegerField(unique=True, db_index=True, null=True, blank=True)
    cid = models.PositiveIntegerField(db_index=True)
    controller = models.ForeignKey(
        Controller, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="live_sessions",
    )
    callsign = models.CharField(max_length=20, db_index=True)
    frequency = models.CharField(max_length=20, blank=True)
    facility = models.PositiveSmallIntegerField(default=0)
    rating = models.PositiveSmallIntegerField(default=1)
    server = models.CharField(max_length=50, blank=True)

    logon_time = models.DateTimeField()
    last_seen = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["-logon_time"]
        verbose_name = "Live Session"
        verbose_name_plural = "Live Sessions"

    def __str__(self):
        return f"{self.callsign} | CID {self.cid} | {'ONLINE' if self.is_active else 'ENDED'}"

    @property
    def duration_minutes(self):
        from django.utils import timezone
        end = self.ended_at or timezone.now()
        return (end - self.logon_time).total_seconds() / 60.0

    @property
    def duration_hours(self):
        return round(self.duration_minutes / 60.0, 2)

    @property
    def rating_label(self):
        return settings.VATSIM_RATINGS.get(self.rating, str(self.rating))
