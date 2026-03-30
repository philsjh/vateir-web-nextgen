from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from apps.controllers.models import ATCSession, LiveSession


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
    my_training = TrainingRequest.objects.filter(student=user).order_by("-created_at").first()

    context = {
        "my_sessions": my_sessions,
        "total_hours": round(total_hours, 1),
        "total_sessions_count": total_sessions_count,
        "live_sessions": live_sessions,
        "upcoming_events": upcoming_events,
        "my_training": my_training,
    }
    return render(request, "dashboard/index.html", context)


@login_required
def my_sessions(request):
    sessions = ATCSession.objects.filter(cid=request.user.cid).order_by("-start")
    return render(request, "dashboard/my_sessions.html", {"sessions": sessions})
