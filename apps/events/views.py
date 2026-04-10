from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.controllers.models import Position
from .models import Event, EventAvailability


def event_list(request):
    upcoming = Event.objects.filter(is_published=True, end_datetime__gte=timezone.now())
    past = Event.objects.filter(is_published=True, end_datetime__lt=timezone.now())[:10]
    return render(request, "events/list.html", {"upcoming": upcoming, "past": past})


def event_detail(request, slug):
    event = get_object_or_404(Event, slug=slug, is_published=True)
    positions = event.positions.select_related("position", "assigned_controller")

    # Determine roster visibility
    show_roster = False
    if event.roster_public:
        show_roster = True
    elif event.roster_published and request.user.is_authenticated:
        show_roster = True

    roster_groups = event.get_roster_groups() if show_roster else []

    user_availability = None
    if request.user.is_authenticated:
        user_availability = EventAvailability.objects.filter(
            event=event, controller=request.user
        ).first()
    return render(request, "events/detail.html", {
        "event": event,
        "positions": positions,
        "roster_groups": roster_groups,
        "show_roster": show_roster,
        "user_availability": user_availability,
    })


@login_required
def sign_up_availability(request, slug):
    event = get_object_or_404(Event, slug=slug, is_published=True)
    event_positions = event.positions.select_related("position").values_list(
        "position_id", flat=True
    ).distinct()
    positions = Position.objects.filter(pk__in=event_positions).order_by("callsign")

    existing = EventAvailability.objects.filter(event=event, controller=request.user).first()

    if request.method == "POST":
        available_from = parse_datetime(request.POST.get("available_from", ""))
        available_to = parse_datetime(request.POST.get("available_to", ""))

        # Validate times are within event bounds
        if available_from and available_from < event.start_datetime:
            available_from = event.start_datetime
        if available_to and available_to > event.end_datetime:
            available_to = event.end_datetime

        availability, created = EventAvailability.objects.get_or_create(
            event=event,
            controller=request.user,
            defaults={
                "notes": request.POST.get("notes", ""),
                "available_from": available_from or event.start_datetime,
                "available_to": available_to or event.end_datetime,
            },
        )
        if not created:
            availability.notes = request.POST.get("notes", "")
            availability.available_from = available_from or event.start_datetime
            availability.available_to = available_to or event.end_datetime
            availability.save()

        # Save preferred positions
        selected_ids = request.POST.getlist("preferred_positions")
        availability.preferred_positions.set(selected_ids)

        messages.success(request, "Your availability has been submitted.")
        return redirect("dashboard:events")

    return render(request, "events/sign_up.html", {
        "event": event,
        "positions": positions,
        "existing": existing,
    })
