import platform
import sys

import django
from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.decorators import rbac_required
from apps.accounts.models import RoleType, SiteConfig, Role, User
from apps.controllers.models import Controller, Position
from apps.training.models import TrainingRequest, TrainingCourse, TrainingCompetency, TrainingTaskDefinition
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
    requests_list = TrainingRequest.objects.all().select_related("student", "course")
    return render(request, "admin_panel/training_list.html", {"training_requests": requests_list})


@rbac_required(RoleType.STAFF)
def training_manage(request, pk):
    tr = get_object_or_404(TrainingRequest.objects.select_related("student", "course"), pk=pk)

    if request.method == "POST":
        tr.status = request.POST.get("status", tr.status)
        pos = request.POST.get("position")
        if pos:
            tr.position = int(pos)
        course_id = request.POST.get("course")
        if course_id:
            tr.course_id = int(course_id) if course_id != "" else None
            if tr.course:
                tr.requested_rating = tr.course.to_rating
        tr.save()
        messages.success(request, "Training request updated.")
        return redirect("admin_panel:training_manage", pk=pk)

    # Courses for assignment dropdown
    courses = TrainingCourse.objects.filter(is_active=True)

    # Time stats
    days_waiting = (timezone.now() - tr.created_at).days
    session_count = tr.sessions.count()
    completed_sessions = tr.sessions.filter(status="COMPLETED").count()
    last_session = tr.sessions.order_by("-session_date").first()

    # VATSIM API member lookup
    import requests as http_requests
    vatsim_member = None
    try:
        resp = http_requests.get(
            f"{settings.VATSIM_API_BASE}/members/{tr.student.cid}",
            timeout=10,
        )
        resp.raise_for_status()
        vatsim_member = resp.json()
    except Exception:
        pass

    # Subdivision check
    subdivision = getattr(settings, "VATSIM_SUBDIVISION", "IRL")
    is_in_subdivision = False
    member_division = ""
    member_subdivision = ""
    member_rating = ""
    member_reg_date = ""
    member_last_rating_change = ""
    if vatsim_member:
        member_division = vatsim_member.get("division_id", "")
        member_subdivision = vatsim_member.get("subdivision_id", "")
        is_in_subdivision = member_subdivision == subdivision
        member_rating = settings.VATSIM_RATINGS.get(vatsim_member.get("rating", 0), "?")
        member_reg_date = vatsim_member.get("reg_date", "")
        member_last_rating_change = vatsim_member.get("lastratingchange", "")

    return render(request, "admin_panel/training_manage.html", {
        "training_request": tr,
        "courses": courses,
        "days_waiting": days_waiting,
        "session_count": session_count,
        "completed_sessions": completed_sessions,
        "last_session": last_session,
        "vatsim_member": vatsim_member,
        "is_in_subdivision": is_in_subdivision,
        "member_division": member_division,
        "member_subdivision": member_subdivision,
        "member_rating": member_rating,
        "member_reg_date": member_reg_date,
        "member_last_rating_change": member_last_rating_change,
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


# --- Training Course Management ---

@rbac_required(RoleType.ADMIN)
def training_courses(request):
    courses = TrainingCourse.objects.prefetch_related("competencies", "task_definitions")
    return render(request, "admin_panel/training_courses.html", {"courses": courses})


@rbac_required(RoleType.ADMIN)
def training_course_edit(request, pk=None):
    course = get_object_or_404(TrainingCourse, pk=pk) if pk else None

    if request.method == "POST":
        if course is None:
            course = TrainingCourse()

        course.name = request.POST.get("name", "")
        course.from_rating = int(request.POST.get("from_rating", 1))
        course.to_rating = int(request.POST.get("to_rating", 2))
        course.description = request.POST.get("description", "")
        course.is_active = request.POST.get("is_active") == "on"
        course.display_order = int(request.POST.get("display_order", 0))
        course.save()

        # Save competencies
        comp_names = request.POST.getlist("comp_name")
        comp_orders = request.POST.getlist("comp_order")
        comp_ids = request.POST.getlist("comp_id")

        existing_comp_ids = set()
        for i, name in enumerate(comp_names):
            name = name.strip()
            if not name:
                continue
            order = int(comp_orders[i]) if i < len(comp_orders) else i
            comp_id = comp_ids[i] if i < len(comp_ids) else ""

            if comp_id:
                comp = TrainingCompetency.objects.filter(pk=int(comp_id), course=course).first()
                if comp:
                    comp.name = name
                    comp.display_order = order
                    comp.save()
                    existing_comp_ids.add(comp.pk)
                    continue

            comp = TrainingCompetency.objects.create(course=course, name=name, display_order=order)
            existing_comp_ids.add(comp.pk)

        # Save task definitions
        task_names = request.POST.getlist("task_name")
        task_orders = request.POST.getlist("task_order")
        task_types = request.POST.getlist("task_session_type")
        task_ids = request.POST.getlist("task_id")

        existing_task_ids = set()
        for i, name in enumerate(task_names):
            name = name.strip()
            if not name:
                continue
            order = int(task_orders[i]) if i < len(task_orders) else i
            stype = task_types[i] if i < len(task_types) else ""
            task_id = task_ids[i] if i < len(task_ids) else ""

            if task_id:
                task = TrainingTaskDefinition.objects.filter(pk=int(task_id), course=course).first()
                if task:
                    task.name = name
                    task.display_order = order
                    task.session_type = stype
                    task.save()
                    existing_task_ids.add(task.pk)
                    continue

            task = TrainingTaskDefinition.objects.create(
                course=course, name=name, display_order=order, session_type=stype
            )
            existing_task_ids.add(task.pk)

        messages.success(request, f"Course '{course.name}' saved.")
        return redirect("admin_panel:training_courses")

    competencies = course.competencies.order_by("display_order") if course else []
    tasks = course.task_definitions.order_by("display_order") if course else []

    from apps.training.models import SessionType
    return render(request, "admin_panel/training_course_edit.html", {
        "course": course,
        "competencies": competencies,
        "tasks": tasks,
        "session_types": SessionType.choices,
    })


# --- Developer Tools ---

# Registry of tasks that can be triggered from the dev tools panel
TRIGGERABLE_TASKS = [
    {
        "id": "poll_live_feed",
        "name": "Poll Live Feed",
        "description": "Fetch VATSIM data feed and update live sessions",
        "task": "apps.controllers.tasks.poll_live_feed",
        "category": "data",
    },
    {
        "id": "fetch_metars",
        "name": "Fetch METARs",
        "description": "Fetch current METARs for configured airports",
        "task": "apps.public.tasks.fetch_metars",
        "category": "data",
    },
    {
        "id": "sync_roster",
        "name": "Sync Roster",
        "description": "Sync subdivision roster from VATSIM API (requires API key)",
        "task": "apps.controllers.tasks.sync_roster",
        "category": "roster",
    },
    {
        "id": "update_all_controller_stats",
        "name": "Update Controller Stats",
        "description": "Update cached stats for all active controllers",
        "task": "apps.controllers.tasks.update_all_controller_stats",
        "category": "roster",
    },
    {
        "id": "backfill_all_controllers",
        "name": "Backfill All Sessions",
        "description": "Backfill ATC session history for all active controllers",
        "task": "apps.controllers.tasks.backfill_all_controllers",
        "category": "roster",
    },
]


@rbac_required(RoleType.ADMIN)
def dev_tools(request):
    from django.core.cache import cache
    from django_celery_results.models import TaskResult

    # Celery broker connection status
    celery_status = {"connected": False, "error": None}
    try:
        from config.celery import app as celery_app
        insp = celery_app.control.inspect(timeout=2)
        ping = insp.ping()
        if ping:
            celery_status["connected"] = True
            celery_status["workers"] = list(ping.keys())
            active = insp.active() or {}
            celery_status["active_tasks"] = sum(len(v) for v in active.values())
            reserved = insp.reserved() or {}
            celery_status["reserved_tasks"] = sum(len(v) for v in reserved.values())
        else:
            celery_status["error"] = "No workers responded to ping"
    except Exception as e:
        celery_status["error"] = str(e)

    # Recent task results
    recent_tasks = TaskResult.objects.order_by("-date_done")[:25]

    # Redis status
    redis_status = {"connected": False, "error": None}
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.CELERY_BROKER_URL)
        info = r.info()
        redis_status["connected"] = True
        redis_status["version"] = info.get("redis_version", "?")
        redis_status["used_memory"] = info.get("used_memory_human", "?")
        redis_status["connected_clients"] = info.get("connected_clients", "?")
        redis_status["keys"] = r.dbsize()
    except Exception as e:
        redis_status["error"] = str(e)

    # Cache stats
    cache_stats = {}
    try:
        last_poll = cache.get("last_live_poll")
        cache_stats["last_live_poll"] = last_poll
        cache_stats["metar_cached"] = bool(cache.get("metar:EIDW"))
        cache_stats["vatsim_feed_cached"] = bool(cache.get("vatsim_data_feed"))
        cache_stats["site_config_cached"] = bool(cache.get("site_config"))
    except Exception:
        pass

    # System info
    sys_info = {
        "python_version": sys.version,
        "django_version": django.get_version(),
        "platform": platform.platform(),
        "debug": settings.DEBUG,
        "database": settings.DATABASES["default"]["ENGINE"],
        "timezone": settings.TIME_ZONE,
        "installed_apps": len(settings.INSTALLED_APPS),
    }

    # DB stats
    db_stats = {
        "controllers": Controller.objects.count(),
        "positions": Position.objects.count(),
        "users": User.objects.count(),
        "events": Event.objects.count(),
        "feedback": Feedback.objects.count(),
        "training_requests": TrainingRequest.objects.count(),
    }

    context = {
        "celery_status": celery_status,
        "recent_tasks": recent_tasks,
        "redis_status": redis_status,
        "cache_stats": cache_stats,
        "sys_info": sys_info,
        "db_stats": db_stats,
        "triggerable_tasks": TRIGGERABLE_TASKS,
    }
    return render(request, "admin_panel/dev_tools.html", context)


@rbac_required(RoleType.ADMIN)
def dev_trigger_task(request):
    """Trigger a Celery task by ID."""
    if request.method != "POST":
        return redirect("admin_panel:dev_tools")

    task_id = request.POST.get("task_id", "")
    task_def = next((t for t in TRIGGERABLE_TASKS if t["id"] == task_id), None)

    if not task_def:
        messages.error(request, f"Unknown task: {task_id}")
        return redirect("admin_panel:dev_tools")

    try:
        from celery import current_app
        current_app.send_task(task_def["task"])
        messages.success(request, f"Task '{task_def['name']}' has been queued.")
    except Exception as e:
        messages.error(request, f"Failed to trigger task: {e}")

    return redirect("admin_panel:dev_tools")


@rbac_required(RoleType.ADMIN)
def dev_clear_cache(request):
    """Clear the entire Redis cache."""
    if request.method != "POST":
        return redirect("admin_panel:dev_tools")

    try:
        from django.core.cache import cache
        cache.clear()
        messages.success(request, "Cache cleared successfully.")
    except Exception as e:
        messages.error(request, f"Failed to clear cache: {e}")

    return redirect("admin_panel:dev_tools")
