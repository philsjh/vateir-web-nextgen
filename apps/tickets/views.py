from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.decorators import permission_required
from apps.accounts.models import User

from .email import email_ticket_reply, email_ticket_resolved
from .models import (
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketReply,
    TicketStatus,
    TicketStatusChange,
)


def _is_staff(user):
    return user.has_permission("tickets.manage") or user.is_superuser


def _notify_discord(func_name, *args, **kwargs):
    """Call a discord notification function, swallowing import/runtime errors."""
    try:
        from apps.notifications import discord
        getattr(discord, func_name)(*args, **kwargs)
    except Exception:
        pass


# ── User-facing views ────────────────────────────────────────────


@login_required
def ticket_list(request):
    tickets = Ticket.objects.filter(created_by=request.user)
    status_filter = request.GET.get("status", "")
    if status_filter:
        tickets = tickets.filter(status=status_filter)
    return render(request, "tickets/list.html", {
        "tickets": tickets,
        "statuses": TicketStatus.choices,
        "current_status": status_filter,
    })


@login_required
def ticket_create(request):
    if request.method == "POST":
        subject = request.POST.get("subject", "").strip()
        description = request.POST.get("description", "").strip()
        category = request.POST.get("category", TicketCategory.GENERAL)
        if not subject or not description:
            messages.error(request, "Subject and description are required.")
            return render(request, "tickets/create.html", {
                "categories": TicketCategory.choices,
                "form_data": request.POST,
            })
        ticket = Ticket.objects.create(
            subject=subject,
            description=description,
            category=category,
            created_by=request.user,
        )
        _notify_discord("notify_new_ticket", ticket)
        messages.success(request, f"Ticket {ticket.reference} created.")
        return redirect("tickets:detail", reference=ticket.reference)
    return render(request, "tickets/create.html", {
        "categories": TicketCategory.choices,
    })


@login_required
def ticket_detail(request, reference):
    ticket = get_object_or_404(Ticket, reference=reference)
    if ticket.created_by != request.user and not _is_staff(request.user):
        return redirect("tickets:list")
    replies = ticket.replies.filter(is_internal_note=False).select_related("author")
    status_changes = ticket.status_changes.select_related("changed_by")
    return render(request, "tickets/detail.html", {
        "ticket": ticket,
        "replies": replies,
        "status_changes": status_changes,
        "is_staff_viewer": _is_staff(request.user),
    })


@login_required
def ticket_reply(request, reference):
    ticket = get_object_or_404(Ticket, reference=reference, created_by=request.user)
    if request.method == "POST":
        if not ticket.is_open:
            messages.error(request, "This ticket is closed and cannot receive replies.")
            return redirect("tickets:detail", reference=reference)
        body = request.POST.get("body", "").strip()
        if body:
            TicketReply.objects.create(
                ticket=ticket, author=request.user, body=body, is_staff_reply=False,
            )
            ticket.last_replied_by = request.user
            ticket.last_replied_at = timezone.now()
            if ticket.status == TicketStatus.AWAITING_USER:
                old = ticket.status
                ticket.status = TicketStatus.OPEN
                ticket.save()
                TicketStatusChange.objects.create(
                    ticket=ticket, changed_by=request.user,
                    old_status=old, new_status=TicketStatus.OPEN,
                    note="User replied",
                )
            else:
                ticket.save(update_fields=["last_replied_by", "last_replied_at", "updated_at"])
            _notify_discord("notify_ticket_reply", ticket, request.user, is_staff=False)
            messages.success(request, "Reply added.")
    return redirect("tickets:detail", reference=reference)


# ── Staff views ──────────────────────────────────────────────────


@permission_required("tickets.manage")
def staff_ticket_list(request):
    tickets = Ticket.objects.select_related("created_by", "assigned_to")
    status_filter = request.GET.get("status", "")
    assigned_filter = request.GET.get("assigned", "")
    priority_filter = request.GET.get("priority", "")
    if status_filter:
        tickets = tickets.filter(status=status_filter)
    if assigned_filter == "me":
        tickets = tickets.filter(assigned_to=request.user)
    elif assigned_filter == "unassigned":
        tickets = tickets.filter(assigned_to__isnull=True)
    if priority_filter:
        tickets = tickets.filter(priority=priority_filter)
    staff_users = User.objects.filter(
        user_roles__role_profile__permissions__codename="tickets.manage"
    ).distinct()
    stats = {
        "open": Ticket.objects.filter(status=TicketStatus.OPEN).count(),
        "in_progress": Ticket.objects.filter(status=TicketStatus.IN_PROGRESS).count(),
        "on_hold": Ticket.objects.filter(status=TicketStatus.ON_HOLD).count(),
        "awaiting_user": Ticket.objects.filter(status=TicketStatus.AWAITING_USER).count(),
        "sla_breached": Ticket.objects.filter(sla_breached=True, status__in=[
            TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.AWAITING_USER,
        ]).count(),
    }
    return render(request, "tickets/staff_list.html", {
        "tickets": tickets,
        "statuses": TicketStatus.choices,
        "priorities": TicketPriority.choices,
        "staff_users": staff_users,
        "current_status": status_filter,
        "current_assigned": assigned_filter,
        "current_priority": priority_filter,
        "stats": stats,
    })


@permission_required("tickets.manage")
def staff_ticket_detail(request, reference):
    ticket = get_object_or_404(
        Ticket.objects.select_related("created_by", "assigned_to"), reference=reference,
    )
    replies = ticket.replies.select_related("author")
    status_changes = ticket.status_changes.select_related("changed_by")
    staff_users = User.objects.filter(
        user_roles__role_profile__permissions__codename="tickets.manage"
    ).distinct()
    return render(request, "tickets/staff_detail.html", {
        "ticket": ticket,
        "replies": replies,
        "status_changes": status_changes,
        "statuses": TicketStatus.choices,
        "priorities": TicketPriority.choices,
        "staff_users": staff_users,
    })


@permission_required("tickets.manage")
def staff_ticket_assign(request, reference):
    ticket = get_object_or_404(Ticket, reference=reference)
    if request.method == "POST":
        assignee_id = request.POST.get("assigned_to")
        if assignee_id:
            assignee = get_object_or_404(User, pk=assignee_id)
            ticket.assigned_to = assignee
        else:
            assignee = None
            ticket.assigned_to = None
        ticket.save()
        name = assignee.vatsim_name if assignee else "Nobody"
        _notify_discord("notify_ticket_assigned", ticket, assignee, request.user)
        messages.success(request, f"Ticket assigned to {name}.")
    return redirect("tickets:staff_detail", reference=reference)


@permission_required("tickets.manage")
def staff_ticket_status(request, reference):
    ticket = get_object_or_404(Ticket, reference=reference)
    if request.method == "POST":
        new_status = request.POST.get("status", "")
        note = request.POST.get("note", "").strip()
        if new_status and new_status != ticket.status and new_status in dict(TicketStatus.choices):
            old_status = ticket.status
            ticket.status = new_status
            if new_status in (TicketStatus.RESOLVED, TicketStatus.CLOSED):
                ticket.closed_at = timezone.now()
            elif old_status in (TicketStatus.RESOLVED, TicketStatus.CLOSED):
                ticket.closed_at = None
            ticket.save()
            TicketStatusChange.objects.create(
                ticket=ticket, changed_by=request.user,
                old_status=old_status, new_status=new_status, note=note,
            )
            _notify_discord("notify_ticket_status_change", ticket, request.user, old_status, new_status)
            if new_status in (TicketStatus.RESOLVED, TicketStatus.CLOSED):
                email_ticket_resolved(ticket, new_status)
            messages.success(request, f"Status changed to {ticket.get_status_display()}.")
    return redirect("tickets:staff_detail", reference=reference)


@permission_required("tickets.manage")
def staff_ticket_priority(request, reference):
    ticket = get_object_or_404(Ticket, reference=reference)
    if request.method == "POST":
        new_priority = request.POST.get("priority", "")
        if new_priority and new_priority in dict(TicketPriority.choices):
            ticket.priority = new_priority
            ticket.save()
            messages.success(request, f"Priority set to {ticket.get_priority_display()}.")
    return redirect("tickets:staff_detail", reference=reference)


@permission_required("tickets.manage")
def staff_ticket_reply(request, reference):
    ticket = get_object_or_404(Ticket, reference=reference)
    if request.method == "POST":
        if not ticket.is_open:
            messages.error(request, "This ticket is closed and cannot receive replies.")
            return redirect("tickets:staff_detail", reference=reference)
        body = request.POST.get("body", "").strip()
        is_internal = request.POST.get("is_internal") == "on"
        if body:
            reply_obj = TicketReply.objects.create(
                ticket=ticket, author=request.user, body=body,
                is_staff_reply=True, is_internal_note=is_internal,
            )
            if not is_internal:
                ticket.last_replied_by = request.user
                ticket.last_replied_at = timezone.now()
            if not is_internal and ticket.status == TicketStatus.OPEN:
                old = ticket.status
                ticket.status = TicketStatus.IN_PROGRESS
                ticket.save()
                TicketStatusChange.objects.create(
                    ticket=ticket, changed_by=request.user,
                    old_status=old, new_status=TicketStatus.IN_PROGRESS,
                    note="Staff replied",
                )
            elif not is_internal:
                ticket.save(update_fields=["last_replied_by", "last_replied_at", "updated_at"])
            if not is_internal:
                _notify_discord("notify_ticket_reply", ticket, request.user, is_staff=True)
                email_ticket_reply(ticket, reply_obj)
            messages.success(request, "Internal note added." if is_internal else "Reply sent.")
    return redirect("tickets:staff_detail", reference=reference)
