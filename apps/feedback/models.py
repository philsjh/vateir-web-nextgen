from django.conf import settings
from django.db import models


class FeedbackType(models.TextChoices):
    COMPLIMENT = "COMPLIMENT", "Compliment"
    CONCERN = "CONCERN", "Concern"
    SUGGESTION = "SUGGESTION", "Suggestion"
    BUG_REPORT = "BUG_REPORT", "Bug Report"


class FeedbackStatus(models.TextChoices):
    NEW = "NEW", "New"
    REVIEWED = "REVIEWED", "Reviewed"
    ACTIONED = "ACTIONED", "Actioned"
    ARCHIVED = "ARCHIVED", "Archived"


class Feedback(models.Model):
    submitter_name = models.CharField(max_length=200, blank=True)
    submitter_email = models.EmailField(blank=True)
    submitter_cid = models.PositiveIntegerField(null=True, blank=True)
    controller_callsign = models.CharField(
        max_length=20, blank=True,
        help_text="Callsign of the controller this feedback is about",
    )
    feedback_type = models.CharField(
        max_length=20, choices=FeedbackType.choices, default=FeedbackType.COMPLIMENT
    )
    content = models.TextField()
    status = models.CharField(
        max_length=20, choices=FeedbackStatus.choices, default=FeedbackStatus.NEW
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="reviewed_feedback",
    )
    admin_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Feedback"
        verbose_name_plural = "Feedback"

    def __str__(self):
        return f"{self.feedback_type} from {self.submitter_name or 'Anonymous'}"
