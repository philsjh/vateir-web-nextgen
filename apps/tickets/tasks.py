import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def check_ticket_sla():
    """Check for tickets that have breached the SLA and notify staff on Discord."""
    from apps.accounts.models import SiteConfig
    from apps.tickets.models import Ticket, TicketStatus

    config = SiteConfig.get()
    sla_hours = config.ticket_sla_hours or 48
    threshold = timezone.now() - timedelta(hours=sla_hours)

    breached = Ticket.objects.filter(
        status__in=[TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.AWAITING_USER],
        created_at__lt=threshold,
        sla_breached=False,
    )

    newly_breached = list(breached)
    if not newly_breached:
        return "No new SLA breaches."

    breached.update(sla_breached=True, sla_breach_notified_at=timezone.now())

    from apps.notifications.discord import notify_ticket_sla_breach
    notify_ticket_sla_breach(newly_breached)

    logger.info("SLA breach: notified for %d tickets", len(newly_breached))
    return f"SLA breach notification sent for {len(newly_breached)} ticket(s)."
