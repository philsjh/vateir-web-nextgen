from django.conf import settings
from django.db import models


class TrainingRequestStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    ACCEPTED = "ACCEPTED", "Accepted"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"


class SessionType(models.TextChoices):
    THEORY = "THEORY", "Theory"
    PRACTICAL = "PRACTICAL", "Practical"
    CPT = "CPT", "Controller Practical Test"
    OTS = "OTS", "Over-The-Shoulder"


class Performance(models.TextChoices):
    BELOW = "BELOW", "Below Expectations"
    MEETS = "MEETS", "Meets Expectations"
    EXCEEDS = "EXCEEDS", "Exceeds Expectations"


class TrainingRequest(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="training_requests"
    )
    requested_rating = models.PositiveSmallIntegerField(
        help_text="The rating being trained towards (e.g. 2=S1, 3=S2)"
    )
    status = models.CharField(
        max_length=20, choices=TrainingRequestStatus.choices,
        default=TrainingRequestStatus.PENDING,
    )
    assigned_mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="mentoring_requests",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Training Request"
        verbose_name_plural = "Training Requests"

    def __str__(self):
        rating_label = settings.VATSIM_RATINGS.get(self.requested_rating, str(self.requested_rating))
        return f"{self.student} → {rating_label} ({self.status})"


class TrainingSession(models.Model):
    training_request = models.ForeignKey(
        TrainingRequest, on_delete=models.CASCADE, related_name="sessions"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="training_sessions_as_student"
    )
    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="training_sessions_as_mentor"
    )
    session_date = models.DateField()
    duration_minutes = models.PositiveIntegerField(default=0)
    position = models.ForeignKey(
        "controllers.Position", on_delete=models.SET_NULL, null=True, blank=True
    )
    session_type = models.CharField(max_length=20, choices=SessionType.choices)
    notes = models.TextField(blank=True)
    student_performance = models.CharField(
        max_length=20, choices=Performance.choices, blank=True
    )
    passed = models.BooleanField(
        null=True, blank=True, help_text="For CPT/OTS sessions"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-session_date"]
        verbose_name = "Training Session"
        verbose_name_plural = "Training Sessions"

    def __str__(self):
        return f"{self.session_type} | {self.student} | {self.session_date}"


class TrainingNote(models.Model):
    training_request = models.ForeignKey(
        TrainingRequest, on_delete=models.CASCADE, related_name="training_notes"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE
    )
    content = models.TextField()
    is_internal = models.BooleanField(
        default=False, help_text="Visible to mentors only"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Training Note"
        verbose_name_plural = "Training Notes"

    def __str__(self):
        return f"Note by {self.author} on {self.created_at:%Y-%m-%d}"
