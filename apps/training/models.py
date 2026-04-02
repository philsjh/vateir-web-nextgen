from django.conf import settings
from django.db import models


class TrainingRequestStatus(models.TextChoices):
    WAITING = "WAITING", "Waiting List"
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
    SIM = "SIM", "Simulator"


class SessionStatus(models.TextChoices):
    SCHEDULED = "SCHEDULED", "Scheduled"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"
    NO_SHOW = "NO_SHOW", "No Show"


# ─── Training Courses (admin-defined) ──────────────────────────────

class TrainingCourse(models.Model):
    """
    A training course defines a path between two ratings.
    e.g. 'OBS → S2', 'S2 → S3', 'S3 → C1'
    """
    name = models.CharField(max_length=100, help_text="e.g. 'OBS → S2'")
    from_rating = models.PositiveSmallIntegerField(
        help_text="Starting rating (1=OBS, 2=S1, etc.)"
    )
    to_rating = models.PositiveSmallIntegerField(
        help_text="Target rating"
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_order", "from_rating"]
        verbose_name = "Training Course"
        verbose_name_plural = "Training Courses"

    def __str__(self):
        return self.name

    @property
    def from_rating_label(self):
        return settings.VATSIM_RATINGS.get(self.from_rating, str(self.from_rating))

    @property
    def to_rating_label(self):
        return settings.VATSIM_RATINGS.get(self.to_rating, str(self.to_rating))


# ─── Competencies (admin-defined per course) ──────────────────────

class TrainingCompetency(models.Model):
    """A competency that students are assessed against in session reports."""
    course = models.ForeignKey(
        TrainingCourse, on_delete=models.CASCADE, related_name="competencies"
    )
    name = models.CharField(max_length=200, help_text="e.g. 'Phraseology', 'Strip Management'")
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "Training Competency"
        verbose_name_plural = "Training Competencies"

    def __str__(self):
        return f"{self.name} ({self.course.name})"


# ─── Task Definitions (admin-defined checklist per course) ────────

class TrainingTaskDefinition(models.Model):
    """
    A required task/milestone in a course. When all tasks are completed,
    the student has finished the course checklist.
    """
    course = models.ForeignKey(
        TrainingCourse, on_delete=models.CASCADE, related_name="task_definitions"
    )
    name = models.CharField(max_length=200, help_text="e.g. 'Ground Theory Exam'")
    description = models.TextField(blank=True)
    session_type = models.CharField(
        max_length=20, choices=SessionType.choices, blank=True,
        help_text="If set, auto-completes when a session of this type is marked completed",
    )
    display_order = models.PositiveIntegerField(default=0)
    is_required = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order"]
        verbose_name = "Training Task"
        verbose_name_plural = "Training Tasks"

    def __str__(self):
        return f"{self.name} ({self.course.name})"


# ─── Training Requests (waiting list) ─────────────────────────────

class TrainingRequest(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="training_requests"
    )
    course = models.ForeignKey(
        TrainingCourse, on_delete=models.CASCADE, related_name="requests",
        null=True, blank=True,
    )
    # Keep for backward compat / direct rating reference
    requested_rating = models.PositiveSmallIntegerField(
        help_text="The rating being trained towards"
    )
    status = models.CharField(
        max_length=20, choices=TrainingRequestStatus.choices,
        default=TrainingRequestStatus.WAITING,
    )
    position = models.PositiveIntegerField(
        default=0, help_text="Position in the waiting list (lower = higher priority)"
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "created_at"]
        verbose_name = "Training Request"
        verbose_name_plural = "Training Requests"

    def __str__(self):
        return f"{self.student} → {self.requested_rating_label} ({self.status})"

    @property
    def requested_rating_label(self):
        return settings.VATSIM_RATINGS.get(self.requested_rating, str(self.requested_rating))

    @property
    def waiting_position(self):
        """1-indexed position among WAITING requests for the same course."""
        if self.status != TrainingRequestStatus.WAITING:
            return None
        ahead = TrainingRequest.objects.filter(
            status=TrainingRequestStatus.WAITING,
            course=self.course,
            position__lt=self.position,
        ).count()
        return ahead + 1

    @property
    def task_completion_pct(self):
        """Percentage of required tasks completed."""
        if not self.course:
            return 0
        total = self.course.task_definitions.filter(is_required=True).count()
        if total == 0:
            return 100
        done = self.task_progress.filter(is_completed=True, task__is_required=True).count()
        return round(done / total * 100)


# ─── Training Sessions ────────────────────────────────────────────

class TrainingSession(models.Model):
    training_request = models.ForeignKey(
        TrainingRequest, on_delete=models.CASCADE, related_name="sessions",
        null=True, blank=True, help_text="Null for adhoc/recurrency sessions",
    )
    is_adhoc = models.BooleanField(
        default=False, help_text="Adhoc session not tied to a training programme"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="training_sessions_as_student"
    )
    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="training_sessions_as_mentor"
    )
    session_date = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(default=0)
    position = models.ForeignKey(
        "controllers.Position", on_delete=models.SET_NULL, null=True, blank=True
    )
    session_type = models.CharField(max_length=20, choices=SessionType.choices)
    status = models.CharField(
        max_length=20, choices=SessionStatus.choices,
        default=SessionStatus.SCHEDULED,
    )
    passed = models.BooleanField(
        null=True, blank=True, help_text="For CPT/OTS sessions"
    )
    notes = models.TextField(blank=True, help_text="Internal mentor notes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-session_date"]
        verbose_name = "Training Session"
        verbose_name_plural = "Training Sessions"

    def __str__(self):
        return f"{self.get_session_type_display()} | {self.student} | {self.session_date:%Y-%m-%d}"

    @property
    def has_report(self):
        try:
            return self.report is not None
        except SessionReport.DoesNotExist:
            return False

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Auto-complete matching task definitions when session is completed
        if self.status == SessionStatus.COMPLETED and self.training_request.course:
            matching_tasks = TrainingTaskDefinition.objects.filter(
                course=self.training_request.course,
                session_type=self.session_type,
            ).exclude(session_type="")
            for task_def in matching_tasks:
                StudentTaskProgress.objects.get_or_create(
                    training_request=self.training_request,
                    task=task_def,
                    defaults={
                        "is_completed": True,
                        "completed_by_session": self,
                    },
                )


# ─── Session Reports ──────────────────────────────────────────────

class SessionReport(models.Model):
    """A report filed by the mentor after a training session."""
    session = models.OneToOneField(
        TrainingSession, on_delete=models.CASCADE, related_name="report"
    )
    summary = models.TextField(
        blank=True, help_text="Overall session summary (Markdown supported)"
    )
    is_published = models.BooleanField(
        default=False,
        help_text="When published, the student can view this report"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Session Report"
        verbose_name_plural = "Session Reports"

    def __str__(self):
        return f"Report for {self.session}"


COMPETENCY_RATING_CHOICES = [
    (0, "N/A"),
    (1, "Poor"),
    (2, "Insufficient"),
    (3, "Acceptable"),
    (4, "Sufficient"),
    (5, "Exam Standard"),
]


class CompetencyRating(models.Model):
    """Individual competency rating within a session report."""
    report = models.ForeignKey(
        SessionReport, on_delete=models.CASCADE, related_name="ratings"
    )
    competency = models.ForeignKey(
        TrainingCompetency, on_delete=models.CASCADE, related_name="ratings"
    )
    rating = models.PositiveSmallIntegerField(
        choices=COMPETENCY_RATING_CHOICES, default=0
    )
    comment = models.TextField(blank=True, help_text="Markdown supported")

    class Meta:
        unique_together = ("report", "competency")
        verbose_name = "Competency Rating"
        verbose_name_plural = "Competency Ratings"

    def __str__(self):
        return f"{self.competency.name}: {self.get_rating_display()}"


# ─── Student Task Progress (checklist) ────────────────────────────

class StudentTaskProgress(models.Model):
    """Tracks completion of task definitions for a student's training request."""
    training_request = models.ForeignKey(
        TrainingRequest, on_delete=models.CASCADE, related_name="task_progress"
    )
    task = models.ForeignKey(
        TrainingTaskDefinition, on_delete=models.CASCADE, related_name="progress"
    )
    is_completed = models.BooleanField(default=False)
    completed_by_session = models.ForeignKey(
        TrainingSession, on_delete=models.SET_NULL, null=True, blank=True
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("training_request", "task")
        verbose_name = "Task Progress"
        verbose_name_plural = "Task Progress"

    def __str__(self):
        status = "Done" if self.is_completed else "Pending"
        return f"{self.task.name}: {status}"


# ─── Training Notes ───────────────────────────────────────────────

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


# ─── Student Availability ─────────────────────────────────────────

class TrainingAvailability(models.Model):
    """A time window when a student is available for training."""
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="training_availability",
    )
    training_request = models.ForeignKey(
        TrainingRequest, on_delete=models.CASCADE, related_name="availability",
        null=True, blank=True,
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    notes = models.TextField(blank=True)
    is_booked = models.BooleanField(default=False)
    booked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="booked_availability",
    )
    booked_session = models.ForeignKey(
        TrainingSession, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="availability_slot",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "start_time"]
        verbose_name = "Training Availability"
        verbose_name_plural = "Training Availability"

    def __str__(self):
        return f"{self.student} — {self.date} {self.start_time}-{self.end_time}"

    @property
    def duration_hours(self):
        from datetime import datetime, date as dt_date
        start = datetime.combine(dt_date.today(), self.start_time)
        end = datetime.combine(dt_date.today(), self.end_time)
        return round((end - start).total_seconds() / 3600, 1)
