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
