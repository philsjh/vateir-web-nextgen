from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Event, EventAvailability


def event_list(request):
    upcoming = Event.objects.filter(is_published=True, end_datetime__gte=timezone.now())
    past = Event.objects.filter(is_published=True, end_datetime__lt=timezone.now())[:10]
    return render(request, "events/list.html", {"upcoming": upcoming, "past": past})


def event_detail(request, slug):
    event = get_object_or_404(Event, slug=slug, is_published=True)
    positions = event.positions.select_related("position", "assigned_controller")
    roster_groups = event.get_roster_groups() if event.roster_published else []
    user_availability = None
    if request.user.is_authenticated:
        user_availability = EventAvailability.objects.filter(
            event=event, controller=request.user
        ).first()
    return render(request, "events/detail.html", {
        "event": event,
        "positions": positions,
        "roster_groups": roster_groups,
        "user_availability": user_availability,
    })


@login_required
def sign_up_availability(request, slug):
    event = get_object_or_404(Event, slug=slug, is_published=True)

    if request.method == "POST":
        availability, created = EventAvailability.objects.get_or_create(
            event=event,
            controller=request.user,
            defaults={"notes": request.POST.get("notes", "")},
        )
        if not created:
            availability.notes = request.POST.get("notes", "")
            availability.save()

        messages.success(request, "Your availability has been submitted.")
        return redirect("dashboard:events")

    return render(request, "events/sign_up.html", {"event": event})
