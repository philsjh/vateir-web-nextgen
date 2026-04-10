from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from .models import Controller, Endorsement, EndorsementType


def roster(request):
    filter_type = request.GET.get("filter", "all")
    controllers = Controller.objects.filter(is_active=True, rating__gte=2).select_related("stats")

    if filter_type == "tier1":
        cids = Endorsement.objects.filter(type=EndorsementType.TIER_1).values_list("cid", flat=True)
        controllers = controllers.filter(cid__in=cids)
    elif filter_type == "tier2":
        cids = Endorsement.objects.filter(type=EndorsementType.TIER_2).values_list("cid", flat=True)
        controllers = controllers.filter(cid__in=cids)

    # Prefetch endorsements for display
    endorsement_map = {}
    for e in Endorsement.objects.filter(cid__in=controllers.values_list("cid", flat=True)):
        endorsement_map.setdefault(e.cid, []).append(e)

    return render(request, "controllers/roster.html", {
        "controllers": controllers,
        "endorsement_map": endorsement_map,
        "filter_type": filter_type,
    })


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

    viewer_authed = request.user.is_authenticated
    results = []
    for c in qs[:20]:
        rating_label = settings.VATSIM_RATINGS.get(c.rating, str(c.rating))
        name = c.get_display_name(viewer_is_authenticated=viewer_authed)
        # Don't show bare CID as name — leave blank so the frontend shows CID only
        if name == str(c.cid):
            name = ""
        results.append({
            "cid": c.cid,
            "name": name,
            "rating": rating_label,
        })
    return JsonResponse(results, safe=False)
