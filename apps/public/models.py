from django.db import models


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
