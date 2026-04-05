from django.conf import settings
from django.db import models


class AnnouncementType(models.TextChoices):
    GENERAL = "GENERAL", "General"
    EVENT = "EVENT", "Event"
    EXAM = "EXAM", "Exam"
    TRAINING = "TRAINING", "Training"


class DiscordBan(models.Model):
    """Tracks bans issued from the website that also apply to Discord."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="discord_bans",
    )
    discord_user_id = models.CharField(max_length=20)
    discord_username = models.CharField(max_length=100, blank=True)
    reason = models.TextField()
    banned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="bans_issued",
    )
    banned_at = models.DateTimeField(auto_now_add=True)
    unbanned_at = models.DateTimeField(null=True, blank=True)
    unbanned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="unbans_issued",
    )
    is_active = models.BooleanField(default=True)
    also_site_banned = models.BooleanField(
        default=False, help_text="Whether the user's website account was also deactivated"
    )
    guild_id = models.CharField(max_length=20)

    class Meta:
        ordering = ["-banned_at"]
        verbose_name = "Discord Ban"
        verbose_name_plural = "Discord Bans"

    def __str__(self):
        return f"Ban: {self.discord_username or self.discord_user_id} ({'active' if self.is_active else 'lifted'})"


class DiscordAnnouncement(models.Model):
    """Log of announcements sent via the control centre."""
    title = models.CharField(max_length=200)
    body = models.TextField()
    channel_id = models.CharField(max_length=20)
    channel_name = models.CharField(max_length=100, blank=True)
    embed_color = models.CharField(max_length=7, default="#059669")
    banner_image_url = models.URLField(blank=True)
    announcement_type = models.CharField(
        max_length=20, choices=AnnouncementType.choices, default=AnnouncementType.GENERAL,
    )
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    sent_at = models.DateTimeField(auto_now_add=True)
    discord_message_id = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["-sent_at"]
        verbose_name = "Discord Announcement"
        verbose_name_plural = "Discord Announcements"

    def __str__(self):
        return f"{self.title} ({self.sent_at:%Y-%m-%d})"


class DiscordBotLog(models.Model):
    """Audit trail of bot actions."""
    action = models.CharField(max_length=50)
    detail = models.TextField(blank=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Bot Log"
        verbose_name_plural = "Bot Logs"

    def __str__(self):
        return f"{self.action} at {self.created_at:%Y-%m-%d %H:%M}"


class MediaUpload(models.Model):
    """Uploaded media files (videos, images) for Discord announcements and embeds."""
    title = models.CharField(max_length=200, blank=True)
    file = models.FileField(upload_to="discord-media/")
    file_size = models.PositiveIntegerField(default=0)
    content_type = models.CharField(max_length=100, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Media Upload"
        verbose_name_plural = "Media Uploads"

    def __str__(self):
        return self.title or self.file.name

    @property
    def url(self):
        return self.file.url if self.file else ""

    @property
    def file_size_display(self):
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.0f} KB"
        else:
            return f"{self.file_size / (1024 * 1024):.1f} MB"

    @property
    def is_video(self):
        return self.content_type.startswith("video/") if self.content_type else False

    @property
    def is_image(self):
        return self.content_type.startswith("image/") if self.content_type else False
