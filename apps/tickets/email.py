import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def _ticket_url(ticket):
    """Build an absolute URL for the user-facing ticket detail."""
    hosts = getattr(settings, "ALLOWED_HOSTS", [])
    domain = hosts[0] if hosts else "localhost:8000"
    scheme = "https" if domain != "localhost:8000" else "http"
    return f"{scheme}://{domain}/tickets/{ticket.reference}/"


def email_ticket_reply(ticket, reply):
    """Email the ticket creator when staff replies."""
    if not ticket.created_by.email:
        return
    try:
        url = _ticket_url(ticket)
        subject = f"[VATéir] Staff reply on {ticket.reference}"
        body = (
            f"Hi,\n\n"
            f"Staff have replied to your support ticket {ticket.reference} "
            f'("{ticket.subject}").\n\n'
            f"---\n{reply.body}\n---\n\n"
            f"View your ticket: {url}\n\n"
            f"VATéir Support"
        )
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [ticket.created_by.email])
    except Exception:
        logger.exception("Failed to send ticket reply email for %s", ticket.reference)


def email_ticket_resolved(ticket, new_status):
    """Email the ticket creator when their ticket is resolved or closed."""
    if not ticket.created_by.email:
        return
    try:
        url = _ticket_url(ticket)
        verb = "resolved" if new_status == "RESOLVED" else "closed"
        subject = f"[VATéir] Ticket {ticket.reference} {verb}"
        body = (
            f"Hi,\n\n"
            f"Your support ticket {ticket.reference} "
            f'("{ticket.subject}") has been {verb}.\n\n'
            f"If you need further help, you can reply to the ticket from your dashboard.\n\n"
            f"View your ticket: {url}\n\n"
            f"VATéir Support"
        )
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [ticket.created_by.email])
    except Exception:
        logger.exception("Failed to send ticket %s email for %s", verb, ticket.reference)
