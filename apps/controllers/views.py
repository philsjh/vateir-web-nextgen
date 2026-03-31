from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from .models import Controller


def roster(request):
    controllers = Controller.objects.filter(is_active=True, rating__gte=2).select_related("stats")
    return render(request, "controllers/roster.html", {"controllers": controllers})


def detail(request, cid):
    controller = get_object_or_404(Controller, pk=cid)
    sessions = controller.sessions.all()[:20]
    return render(request, "controllers/detail.html", {
        "controller": controller,
        "sessions": sessions,
    })


def search_api(request):
    """JSON API for searching controllers by CID or name. Used by Tom Select."""
    q = request.GET.get("q", "").strip()
    if not q:
        return JsonResponse([], safe=False)

    from django.conf import settings
    from django.db.models import Q, Value
    from django.db.models.functions import Cast
    from django.db.models import CharField

    qs = Controller.objects.filter(is_active=True, rating__gte=2)

    if q.isdigit():
        # Cast CID to string for prefix matching
        qs = qs.annotate(cid_str=Cast("cid", CharField())).filter(cid_str__startswith=q)
    else:
        # Match first or last name
        qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q))

    results = []
    for c in qs[:20]:
        rating_label = settings.VATSIM_RATINGS.get(c.rating, str(c.rating))
        name = c.display_name if c.display_name != str(c.cid) else ""
        results.append({
            "cid": c.cid,
            "name": name,
            "rating": rating_label,
        })
    return JsonResponse(results, safe=False)
