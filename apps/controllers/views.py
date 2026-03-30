from django.shortcuts import get_object_or_404, render
from .models import Controller


def roster(request):
    controllers = Controller.objects.filter(is_active=True).select_related("stats")
    return render(request, "controllers/roster.html", {"controllers": controllers})


def detail(request, cid):
    controller = get_object_or_404(Controller, pk=cid)
    sessions = controller.sessions.all()[:20]
    return render(request, "controllers/detail.html", {
        "controller": controller,
        "sessions": sessions,
    })
