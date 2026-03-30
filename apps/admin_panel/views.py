from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators import rbac_required
from apps.accounts.models import RoleType, SiteConfig, Role, User
from apps.controllers.models import Controller, Position
from apps.training.models import TrainingRequest
from apps.events.models import Event
from apps.feedback.models import Feedback


@rbac_required(RoleType.STAFF)
def overview(request):
    context = {
        "total_controllers": Controller.objects.count(),
        "active_controllers": Controller.objects.filter(is_active=True).count(),
        "pending_training": TrainingRequest.objects.filter(status="PENDING").count(),
        "upcoming_events": Event.objects.filter(is_published=True).count(),
        "new_feedback": Feedback.objects.filter(status="NEW").count(),
    }
    return render(request, "admin_panel/overview.html", context)


# --- Controllers Management ---

@rbac_required(RoleType.STAFF)
def controllers_list(request):
    controllers = Controller.objects.all().select_related("stats")
    return render(request, "admin_panel/controllers_list.html", {"controllers": controllers})


@rbac_required(RoleType.STAFF)
def controller_edit(request, cid):
    controller = get_object_or_404(Controller, pk=cid)
    if request.method == "POST":
        controller.first_name = request.POST.get("first_name", "")
        controller.last_name = request.POST.get("last_name", "")
        controller.email = request.POST.get("email", "")
        controller.rating = int(request.POST.get("rating", 1))
        controller.is_active = request.POST.get("is_active") == "on"
        controller.is_home_controller = request.POST.get("is_home_controller") == "on"
        controller.notes = request.POST.get("notes", "")
        controller.save()
        messages.success(request, f"Controller {controller.cid} updated.")
        return redirect("admin_panel:controllers_list")
    return render(request, "admin_panel/controller_edit.html", {"controller": controller})


# --- Training Management ---

@rbac_required(RoleType.STAFF)
def training_list(request):
    requests_list = TrainingRequest.objects.all().select_related("student", "assigned_mentor")
    return render(request, "admin_panel/training_list.html", {"training_requests": requests_list})


@rbac_required(RoleType.STAFF)
def training_manage(request, pk):
    tr = get_object_or_404(TrainingRequest, pk=pk)
    if request.method == "POST":
        tr.status = request.POST.get("status", tr.status)
        mentor_id = request.POST.get("assigned_mentor")
        if mentor_id:
            tr.assigned_mentor_id = int(mentor_id)
        tr.save()
        messages.success(request, "Training request updated.")
        return redirect("admin_panel:training_list")

    mentors = User.objects.filter(roles__role__in=[RoleType.MENTOR, RoleType.EXAMINER]).distinct()
    return render(request, "admin_panel/training_manage.html", {
        "training_request": tr,
        "mentors": mentors,
    })


# --- Events Management ---

@rbac_required(RoleType.STAFF)
def events_list(request):
    events = Event.objects.all()
    return render(request, "admin_panel/events_list.html", {"events": events})


@rbac_required(RoleType.STAFF)
def event_create(request):
    if request.method == "POST":
        from django.utils.text import slugify
        title = request.POST.get("title", "")
        event = Event.objects.create(
            title=title,
            slug=slugify(title),
            description=request.POST.get("description", ""),
            start_datetime=request.POST.get("start_datetime"),
            end_datetime=request.POST.get("end_datetime"),
            airport_icao=request.POST.get("airport_icao", ""),
            is_published=request.POST.get("is_published") == "on",
            is_featured=request.POST.get("is_featured") == "on",
            banner_url=request.POST.get("banner_url", ""),
            created_by=request.user,
        )
        messages.success(request, f"Event '{event.title}' created.")
        return redirect("admin_panel:event_edit", pk=event.pk)
    return render(request, "admin_panel/event_form.html", {"event": None})


@rbac_required(RoleType.STAFF)
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if request.method == "POST":
        event.title = request.POST.get("title", event.title)
        event.description = request.POST.get("description", event.description)
        event.start_datetime = request.POST.get("start_datetime")
        event.end_datetime = request.POST.get("end_datetime")
        event.airport_icao = request.POST.get("airport_icao", "")
        event.is_published = request.POST.get("is_published") == "on"
        event.is_featured = request.POST.get("is_featured") == "on"
        event.banner_url = request.POST.get("banner_url", "")
        event.save()
        messages.success(request, f"Event '{event.title}' updated.")
        return redirect("admin_panel:events_list")
    return render(request, "admin_panel/event_form.html", {"event": event})


# --- Feedback Management ---

@rbac_required(RoleType.STAFF)
def feedback_list(request):
    feedback = Feedback.objects.all()
    return render(request, "admin_panel/feedback_list.html", {"feedback_items": feedback})


@rbac_required(RoleType.STAFF)
def feedback_review(request, pk):
    fb = get_object_or_404(Feedback, pk=pk)
    if request.method == "POST":
        fb.status = request.POST.get("status", fb.status)
        fb.admin_notes = request.POST.get("admin_notes", "")
        fb.reviewed_by = request.user
        fb.save()
        messages.success(request, "Feedback updated.")
        return redirect("admin_panel:feedback_list")
    return render(request, "admin_panel/feedback_review.html", {"feedback": fb})


# --- Roles Management ---

@rbac_required(RoleType.ADMIN)
def roles_manage(request):
    if request.method == "POST":
        user_id = request.POST.get("user_id")
        role_type = request.POST.get("role")
        action = request.POST.get("action")
        try:
            target_user = User.objects.get(pk=int(user_id))
            if action == "grant":
                Role.objects.get_or_create(
                    user=target_user, role=role_type,
                    defaults={"granted_by": request.user},
                )
                messages.success(request, f"Granted {role_type} to {target_user}.")
            elif action == "revoke":
                Role.objects.filter(user=target_user, role=role_type).delete()
                messages.success(request, f"Revoked {role_type} from {target_user}.")
        except User.DoesNotExist:
            messages.error(request, "User not found.")
        return redirect("admin_panel:roles_manage")

    users_with_roles = User.objects.filter(roles__isnull=False).distinct().prefetch_related("roles")
    return render(request, "admin_panel/roles_manage.html", {
        "users_with_roles": users_with_roles,
        "role_types": RoleType.choices,
    })


# --- Site Configuration ---

@rbac_required(RoleType.ADMIN)
def site_config(request):
    config = SiteConfig.get()
    if request.method == "POST":
        config.site_name = request.POST.get("site_name", config.site_name)
        config.topbar_text = request.POST.get("topbar_text", config.topbar_text)
        config.fir_name = request.POST.get("fir_name", config.fir_name)
        config.fir_long_name = request.POST.get("fir_long_name", config.fir_long_name)
        config.callsign_prefixes = request.POST.get("callsign_prefixes", config.callsign_prefixes)
        config.metar_icaos = request.POST.get("metar_icaos", config.metar_icaos)
        config.hero_title = request.POST.get("hero_title", config.hero_title)
        config.hero_subtitle = request.POST.get("hero_subtitle", config.hero_subtitle)
        config.primary_color_from = request.POST.get("primary_color_from", config.primary_color_from)
        config.primary_color_to = request.POST.get("primary_color_to", config.primary_color_to)
        config.enable_metar_widget = request.POST.get("enable_metar_widget") == "on"
        config.enable_events_page = request.POST.get("enable_events_page") == "on"
        config.enable_feedback_page = request.POST.get("enable_feedback_page") == "on"
        config.discord_webhook_url = request.POST.get("discord_webhook_url", "")
        config.save()
        messages.success(request, "Site configuration updated.")
        return redirect("admin_panel:site_config")
    return render(request, "admin_panel/site_config.html", {"config": config})
