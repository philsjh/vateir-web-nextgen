from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.controllers.models import ATCSession, LiveSession
from apps.events.models import Event, EventAvailability


@login_required
def index(request):
    user = request.user
    # Personal stats
    my_sessions = ATCSession.objects.filter(cid=user.cid).order_by("-start")[:10]
    total_hours = sum(s.duration_hours for s in ATCSession.objects.filter(cid=user.cid))
    total_sessions_count = ATCSession.objects.filter(cid=user.cid).count()

    # Live sessions
    live_sessions = LiveSession.objects.filter(is_active=True)

    # Upcoming events
    from apps.events.models import Event
    upcoming_events = Event.objects.filter(
        is_published=True, start_datetime__gte=timezone.now()
    ).order_by("start_datetime")[:5]

    # Training status
    from apps.training.models import TrainingRequest
    from apps.controllers.models import Controller, VisitorStatus
    my_training = TrainingRequest.objects.filter(student=user).order_by("-created_at").first()

    # Check if home controller with C1+ (rating >= 5) — training complete
    training_complete = False
    if user.rating >= 5:
        controller = Controller.objects.filter(cid=user.cid).first()
        if controller and controller.is_home_controller:
            training_complete = True

    context = {
        "my_sessions": my_sessions,
        "total_hours": round(total_hours, 1),
        "total_sessions_count": total_sessions_count,
        "live_sessions": live_sessions,
        "upcoming_events": upcoming_events,
        "my_training": my_training,
        "training_complete": training_complete,
    }
    return render(request, "dashboard/index.html", context)


@login_required
def my_sessions(request):
    sessions = ATCSession.objects.filter(cid=request.user.cid).order_by("-start")
    return render(request, "dashboard/my_sessions.html", {"sessions": sessions})


@login_required
def events(request):
    now = timezone.now()
    upcoming = (
        Event.objects.filter(is_published=True, end_datetime__gte=now)
        .order_by("start_datetime")
    )

    signed_up_ids = set(
        EventAvailability.objects.filter(
            controller=request.user, event__in=upcoming
        ).values_list("event_id", flat=True)
    )

    events_list = []
    for event in upcoming:
        events_list.append({
            "event": event,
            "signed_up": event.pk in signed_up_ids,
            "position_count": event.positions.count(),
            "filled_count": event.positions.filter(is_filled=True).count(),
        })

    return render(request, "dashboard/events.html", {"events_list": events_list})


@login_required
def event_detail(request, slug):
    event = get_object_or_404(Event, slug=slug, is_published=True)
    availability = EventAvailability.objects.filter(
        event=event, controller=request.user
    ).first()

    positions = event.positions.select_related("position", "assigned_controller")
    roster_groups = event.get_roster_groups() if event.roster_published else []

    # Check if the user is assigned to any position
    my_positions = [
        ep for ep in positions if ep.assigned_controller_id == request.user.pk
    ]

    return render(request, "dashboard/event_detail.html", {
        "event": event,
        "availability": availability,
        "roster_groups": roster_groups,
        "my_positions": my_positions,
    })


@login_required
def event_remove_availability(request, slug):
    if request.method == "POST":
        event = get_object_or_404(Event, slug=slug, is_published=True)
        EventAvailability.objects.filter(event=event, controller=request.user).delete()
        messages.success(request, "Your availability has been removed.")
    return redirect("dashboard:event_detail", slug=slug)
