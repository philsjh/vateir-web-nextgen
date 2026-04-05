import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class TicketStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    AWAITING_USER = "AWAITING_USER", "Awaiting User Response"
    ON_HOLD = "ON_HOLD", "On Hold"
    RESOLVED = "RESOLVED", "Resolved"
    CLOSED = "CLOSED", "Closed"


class TicketPriority(models.TextChoices):
    LOW = "LOW", "Low"
    MEDIUM = "MEDIUM", "Medium"
    HIGH = "HIGH", "High"
    URGENT = "URGENT", "Urgent"


class TicketCategory(models.TextChoices):
    GENERAL = "GENERAL", "General Enquiry"
    TECHNICAL = "TECHNICAL", "Technical Issue"
    TRAINING = "TRAINING", "Training"
    EVENTS = "EVENTS", "Events"
    MEMBERSHIP = "MEMBERSHIP", "Membership"
    OTHER = "OTHER", "Other"


class Ticket(models.Model):
    reference = models.CharField(
        max_length=12, unique=True, editable=False,
        help_text="Public ticket reference (e.g. TK-A1B2C3)",
    )
    subject = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(
        max_length=20, choices=TicketCategory.choices, default=TicketCategory.GENERAL,
    )
    priority = models.CharField(
        max_length=10, choices=TicketPriority.choices, default=TicketPriority.MEDIUM,
    )
    status = models.CharField(
        max_length=20, choices=TicketStatus.choices, default=TicketStatus.OPEN,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tickets",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="assigned_tickets",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    sla_breached = models.BooleanField(default=False)
    sla_breach_notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Support Ticket"
        verbose_name_plural = "Support Tickets"

    def __str__(self):
        return f"{self.reference} — {self.subject}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"TK-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    @property
    def is_open(self):
        return self.status not in (TicketStatus.RESOLVED, TicketStatus.CLOSED)

    @property
    def age_hours(self):
        end = self.closed_at or timezone.now()
        return (end - self.created_at).total_seconds() / 3600


class TicketReply(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ticket_replies",
    )
    body = models.TextField()
    is_staff_reply = models.BooleanField(default=False)
    is_internal_note = models.BooleanField(
        default=False, help_text="Internal notes visible to staff only",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Ticket Reply"
        verbose_name_plural = "Ticket Replies"

    def __str__(self):
        return f"Reply on {self.ticket.reference} by {self.author}"


class TicketStatusChange(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="status_changes")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
    )
    old_status = models.CharField(max_length=20, choices=TicketStatus.choices)
    new_status = models.CharField(max_length=20, choices=TicketStatus.choices)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.ticket.reference}: {self.old_status} -> {self.new_status}"
