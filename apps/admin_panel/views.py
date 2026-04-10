import platform
import sys

import django
from django.conf import settings
from django.db import models
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.decorators import permission_required
from apps.accounts.models import SiteConfig, User, RoleProfile, UserRole, Permission, UserPermission
from apps.controllers.models import Controller, ControllerNote, Position, PositionType, Endorsement, EndorsementType
from apps.training.models import TrainingRequest, TrainingSession, TrainingCourse, TrainingCompetency, TrainingTaskDefinition, SessionType
from apps.events.models import Event, EventPosition, EventAvailability
from apps.feedback.models import Feedback
from apps.notifications.models import DiscordBan, DiscordAnnouncement, DiscordBotLog
from apps.public.models import StaffMember, Document, DocumentCategory, Airport, Runway
from apps.tickets.models import Ticket, TicketStatus


@permission_required("admin_panel.access")
def overview(request):
    context = {
        "total_controllers": Controller.objects.count(),
        "active_controllers": Controller.objects.filter(is_active=True).count(),
        "pending_training": TrainingRequest.objects.filter(status="PENDING").count(),
        "upcoming_events": Event.objects.filter(is_published=True).count(),
        "new_feedback": Feedback.objects.filter(status="NEW").count(),
        "open_tickets": Ticket.objects.filter(status__in=[TicketStatus.OPEN, TicketStatus.IN_PROGRESS]).count(),
    }
    return render(request, "admin_panel/overview.html", context)


# --- Controllers Management ---

@permission_required("admin_panel.access")
def members_list(request):
    members = User.objects.all().order_by("-last_login")
    search = request.GET.get("q", "").strip()
    if search:
        members = members.filter(
            models.Q(vatsim_name__icontains=search) |
            models.Q(cid__icontains=search) |
            models.Q(email__icontains=search) |
            models.Q(username__icontains=search)
        )
    return render(request, "admin_panel/members_list.html", {
        "members": members[:200],
        "search": search,
        "total_count": User.objects.count(),
    })


@permission_required("controllers.manage")
def controllers_list(request):
    filter_type = request.GET.get("filter", "active")
    controllers = Controller.objects.filter(rating__gte=2).select_related("stats")

    if filter_type == "active":
        controllers = controllers.filter(on_roster=True)
    elif filter_type == "inactive":
        controllers = controllers.filter(on_roster=False)
    elif filter_type == "tier1":
        cids = Endorsement.objects.filter(type=EndorsementType.TIER_1).values_list("cid", flat=True)
        controllers = controllers.filter(cid__in=cids)
    elif filter_type == "tier2":
        cids = Endorsement.objects.filter(type=EndorsementType.TIER_2).values_list("cid", flat=True)
        controllers = controllers.filter(cid__in=cids)
    # "all" shows everything

    endorsement_map = {}
    for e in Endorsement.objects.filter(cid__in=controllers.values_list("cid", flat=True)):
        endorsement_map.setdefault(e.cid, []).append(e)

    return render(request, "admin_panel/controllers_list.html", {
        "controllers": controllers,
        "endorsement_map": endorsement_map,
        "filter_type": filter_type,
    })


@permission_required("controllers.manage")
def controller_edit(request, cid):
    controller = get_object_or_404(Controller, pk=cid)
    if request.method == "POST":
        controller.first_name = request.POST.get("first_name", "")
        controller.last_name = request.POST.get("last_name", "")
        controller.email = request.POST.get("email", "")
        controller.rating = int(request.POST.get("rating", 1))
        controller.is_active = request.POST.get("is_active") == "on"
        from apps.controllers.models import VisitorStatus
        new_visitor_status = request.POST.get("visitor_status", controller.visitor_status)
        if new_visitor_status != controller.visitor_status:
            controller.visitor_status = new_visitor_status
            if new_visitor_status == VisitorStatus.APPROVED:
                controller.visitor_approved_by = request.user
                controller.visitor_approved_at = timezone.now()
        controller.notes = request.POST.get("notes", "")
        controller.save()
        messages.success(request, f"Controller {controller.cid} updated.")
        return redirect("admin_panel:controllers_list")
    return render(request, "admin_panel/controller_edit.html", {"controller": controller})


@permission_required("controllers.manage")
def controller_profile(request, cid):
    controller = get_object_or_404(Controller.objects.select_related("stats"), pk=cid)

    # Handle POST: add staff note or create adhoc session
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add_note":
            content = request.POST.get("content", "").strip()
            if content:
                ControllerNote.objects.create(
                    controller=controller,
                    author=request.user,
                    content=content,
                )
                messages.success(request, "Staff note added.")
            return redirect("admin_panel:controller_profile", cid=cid)

        elif action == "create_adhoc":
            from apps.accounts.models import User
            session_date = request.POST.get("session_date")
            duration = int(request.POST.get("duration_minutes", 60))
            session_type = request.POST.get("session_type", "PRACTICAL")
            notes = request.POST.get("notes", "")
            # Find or skip student user
            student_user = User.objects.filter(cid=cid).first()
            if student_user and session_date:
                TrainingSession.objects.create(
                    training_request=None,
                    is_adhoc=True,
                    student=student_user,
                    mentor=request.user,
                    session_date=session_date,
                    duration_minutes=duration,
                    session_type=session_type,
                    status="COMPLETED",
                    notes=notes,
                )
                messages.success(request, "Adhoc training session created.")
            else:
                messages.error(request, "Could not create session. Ensure the controller has a linked user account.")
            return redirect("admin_panel:controller_profile", cid=cid)

    # Staff notes
    staff_notes = controller.staff_notes.select_related("author").all()

    # All training sessions for this controller (via User)
    from apps.accounts.models import User
    student_user = User.objects.filter(cid=cid).first()
    programme_sessions = []
    adhoc_sessions = []
    if student_user:
        all_sessions = TrainingSession.objects.filter(
            student=student_user,
        ).select_related("mentor", "training_request__course").order_by("-session_date")
        programme_sessions = [s for s in all_sessions if not s.is_adhoc]
        adhoc_sessions = [s for s in all_sessions if s.is_adhoc]

    # VATSIM API member lookup (same pattern as training_manage)
    import requests as http_requests
    vatsim_member = None
    try:
        resp = http_requests.get(
            f"{settings.VATSIM_API_BASE}/members/{cid}",
            timeout=10,
        )
        resp.raise_for_status()
        vatsim_member = resp.json()
    except Exception:
        pass

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

    return render(request, "admin_panel/controller_profile.html", {
        "controller": controller,
        "staff_notes": staff_notes,
        "programme_sessions": programme_sessions,
        "adhoc_sessions": adhoc_sessions,
        "all_sessions": programme_sessions + adhoc_sessions,
        "student_user": student_user,
        "session_types": SessionType.choices,
        "vatsim_member": vatsim_member,
        "is_in_subdivision": is_in_subdivision,
        "member_division": member_division,
        "member_subdivision": member_subdivision,
        "member_rating": member_rating,
        "member_reg_date": member_reg_date,
        "member_last_rating_change": member_last_rating_change,
    })


# --- Training Management ---

@permission_required("training.manage")
def training_list(request):
    status_filter = request.GET.get("status", "active")
    if status_filter == "all":
        requests_list = TrainingRequest.objects.all()
    elif status_filter == "active":
        requests_list = TrainingRequest.objects.filter(
            status__in=["WAITING", "ACCEPTED", "IN_PROGRESS"]
        )
    else:
        requests_list = TrainingRequest.objects.filter(status=status_filter)

    requests_list = requests_list.select_related("student", "course").order_by("position", "created_at")

    return render(request, "admin_panel/training_list.html", {
        "training_requests": requests_list,
        "status_filter": status_filter,
    })


@permission_required("training.manage")
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

@permission_required("events.manage")
def events_list(request):
    events = Event.objects.select_related("airport").all()
    return render(request, "admin_panel/events_list.html", {"events": events})


@permission_required("events.manage")
def event_create(request):
    airports = Airport.objects.filter(is_visible=True)
    if request.method == "POST":
        from django.utils.text import slugify
        title = request.POST.get("title", "")
        airport_id = request.POST.get("airport") or None
        event = Event(
            title=title,
            slug=slugify(title),
            description=request.POST.get("description", ""),
            start_datetime=request.POST.get("start_datetime"),
            end_datetime=request.POST.get("end_datetime"),
            airport_id=airport_id,
            is_published=request.POST.get("is_published") == "on",
            is_featured=request.POST.get("is_featured") == "on",
            banner_url=request.POST.get("banner_url", ""),
            created_by=request.user,
        )
        if request.FILES.get("banner_image"):
            event.banner_image = request.FILES["banner_image"]
        event.save()
        messages.success(request, f"Event '{event.title}' created.")
        return redirect("admin_panel:event_edit", pk=event.pk)
    return render(request, "admin_panel/event_form.html", {"event": None, "airports": airports})


@permission_required("events.manage")
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)
    airports = Airport.objects.filter(is_visible=True)
    if request.method == "POST":
        event.title = request.POST.get("title", event.title)
        event.description = request.POST.get("description", event.description)
        event.start_datetime = request.POST.get("start_datetime")
        event.end_datetime = request.POST.get("end_datetime")
        event.airport_id = request.POST.get("airport") or None
        event.is_published = request.POST.get("is_published") == "on"
        event.is_featured = request.POST.get("is_featured") == "on"
        event.banner_url = request.POST.get("banner_url", "")
        if request.FILES.get("banner_image"):
            event.banner_image = request.FILES["banner_image"]
        event.save()
        messages.success(request, f"Event '{event.title}' updated.")
        return redirect("admin_panel:events_list")
    return render(request, "admin_panel/event_form.html", {"event": event, "airports": airports})


# --- Feedback Management ---

@permission_required("feedback.manage")
def feedback_list(request):
    status_filter = request.GET.get("status", "active")
    if status_filter == "all":
        feedback = Feedback.objects.all()
    elif status_filter == "active":
        feedback = Feedback.objects.filter(status__in=["NEW", "REVIEWED"])
    else:
        feedback = Feedback.objects.filter(status=status_filter)
    feedback = feedback.select_related("controller", "reviewed_by")
    return render(request, "admin_panel/feedback_list.html", {
        "feedback_items": feedback,
        "status_filter": status_filter,
    })


@permission_required("feedback.manage")
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


@permission_required("training.manage")
def training_course_delete(request, pk):
    if request.method == "POST":
        course = get_object_or_404(TrainingCourse, pk=pk)
        name = course.name
        course.delete()
        messages.success(request, f"Course '{name}' deleted.")
    return redirect("admin_panel:training_courses")


# --- Staff Page Management ---

@permission_required("staff_page.manage")
def staff_list(request):
    staff = StaffMember.objects.all()
    return render(request, "admin_panel/staff_list.html", {"staff_members": staff})


@permission_required("staff_page.manage")
def staff_edit(request, pk=None):
    member = get_object_or_404(StaffMember, pk=pk) if pk else None

    if request.method == "POST":
        if member is None:
            member = StaffMember()

        member.name = request.POST.get("name", "")
        member.position_title = request.POST.get("position_title", "")
        member.bio = request.POST.get("bio", "")
        member.avatar_url = request.POST.get("avatar_url", "")
        member.display_order = int(request.POST.get("display_order", 0))
        member.is_active = request.POST.get("is_active") == "on"

        user_id = request.POST.get("user_id")
        if user_id:
            member.user_id = int(user_id)
        else:
            member.user = None

        member.save()
        messages.success(request, f"Staff member '{member.name}' saved.")
        return redirect("admin_panel:staff_list")

    users = User.objects.filter(user_roles__isnull=False).distinct().order_by("vatsim_name")
    return render(request, "admin_panel/staff_edit.html", {
        "member": member,
        "users": users,
    })


@permission_required("staff_page.manage")
def staff_delete(request, pk):
    if request.method == "POST":
        member = get_object_or_404(StaffMember, pk=pk)
        name = member.name
        member.delete()
        messages.success(request, f"Staff member '{name}' removed.")
    return redirect("admin_panel:staff_list")


# --- Roles Management ---

@permission_required("roles.manage")
def roles_manage(request):
    if request.method == "POST":
        user_id = request.POST.get("user_id")
        action = request.POST.get("action")
        try:
            target_user = User.objects.get(pk=int(user_id))

            if action == "grant_role":
                profile_id = request.POST.get("role_profile_id")
                profile = RoleProfile.objects.get(pk=int(profile_id))
                UserRole.objects.get_or_create(
                    user=target_user, role_profile=profile,
                    defaults={"granted_by": request.user},
                )
                messages.success(request, f"Granted '{profile.name}' to {target_user}.")

            elif action == "revoke_role":
                profile_id = request.POST.get("role_profile_id")
                UserRole.objects.filter(user=target_user, role_profile_id=int(profile_id)).delete()
                messages.success(request, f"Revoked role from {target_user}.")

            elif action == "grant_permission":
                perm_id = request.POST.get("permission_id")
                perm = Permission.objects.get(pk=int(perm_id))
                UserPermission.objects.get_or_create(
                    user=target_user, permission=perm,
                    defaults={"granted_by": request.user},
                )
                messages.success(request, f"Granted '{perm.name}' to {target_user}.")

            elif action == "revoke_permission":
                perm_id = request.POST.get("permission_id")
                UserPermission.objects.filter(user=target_user, permission_id=int(perm_id)).delete()
                messages.success(request, f"Revoked permission from {target_user}.")

        except (User.DoesNotExist, RoleProfile.DoesNotExist, Permission.DoesNotExist):
            messages.error(request, "User, role, or permission not found.")
        except (ValueError, TypeError):
            messages.error(request, "Invalid input.")
        return redirect("admin_panel:roles_manage")

    assigned_users = (
        User.objects.filter(
            models.Q(user_roles__isnull=False) | models.Q(direct_permissions__isnull=False)
        )
        .distinct()
        .prefetch_related("user_roles__role_profile", "direct_permissions__permission")
        .order_by("vatsim_name")
    )
    all_users = User.objects.order_by("vatsim_name").values("pk", "vatsim_name", "cid")
    permissions = Permission.objects.order_by("category", "name")

    return render(request, "admin_panel/roles_manage.html", {
        "assigned_users": assigned_users,
        "all_users": all_users,
        "role_profiles": RoleProfile.objects.prefetch_related("permissions").order_by("name"),
        "permissions": permissions,
    })


# --- Site Configuration ---

@permission_required("admin_panel.site_config")
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
        config.enable_tickets = request.POST.get("enable_tickets") == "on"
        config.ticket_sla_hours = int(request.POST.get("ticket_sla_hours", config.ticket_sla_hours) or config.ticket_sla_hours)
        config.discord_webhook_url = request.POST.get("discord_webhook_url", "")
        config.discord_guild_id = request.POST.get("discord_guild_id", "")
        config.discord_roster_channel_id = request.POST.get("discord_roster_channel_id", "")
        config.discord_training_channel_id = request.POST.get("discord_training_channel_id", "")
        config.discord_events_channel_id = request.POST.get("discord_events_channel_id", "")
        config.discord_general_channel_id = request.POST.get("discord_general_channel_id", "")
        config.discord_tickets_channel_id = request.POST.get("discord_tickets_channel_id", "")
        config.discord_feedback_channel_id = request.POST.get("discord_feedback_channel_id", "")
        config.save()
        messages.success(request, "Site configuration updated.")
        return redirect("admin_panel:site_config")

    # Fetch Discord guild info + channels if configured
    discord_guild = None
    discord_channels = []
    if config.discord_guild_id and settings.DISCORD_BOT_TOKEN:
        from apps.notifications.discord import get_guild_info, get_guild_channels
        discord_guild = get_guild_info(config.discord_guild_id)
        discord_channels = get_guild_channels(config.discord_guild_id)

    return render(request, "admin_panel/site_config.html", {
        "config": config,
        "discord_guild": discord_guild,
        "discord_channels": discord_channels,
    })


@permission_required("admin_panel.site_config")
def discord_channels_api(request):
    """AJAX endpoint to fetch Discord channels for a guild ID."""
    from django.http import JsonResponse
    guild_id = request.GET.get("guild_id", "")
    if not guild_id or not settings.DISCORD_BOT_TOKEN:
        return JsonResponse([], safe=False)
    from apps.notifications.discord import get_guild_channels
    channels = get_guild_channels(guild_id)
    return JsonResponse(channels, safe=False)


# --- Training Course Management ---

@permission_required("training.manage")
def training_courses(request):
    courses = TrainingCourse.objects.prefetch_related("competencies", "task_definitions")
    return render(request, "admin_panel/training_courses.html", {"courses": courses})


@permission_required("training.manage")
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


# --- Document Library Management ---

@permission_required("documents.manage")
def documents_list(request):
    documents = Document.objects.select_related("category", "uploaded_by").all()
    return render(request, "admin_panel/documents_list.html", {"documents": documents})


@permission_required("documents.manage")
def document_upload(request):
    if request.method == "POST":
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            messages.error(request, "No file was uploaded.")
            return redirect("admin_panel:document_upload")

        category_id = request.POST.get("category")
        doc = Document(
            title=request.POST.get("title", uploaded_file.name),
            description=request.POST.get("description", ""),
            category_id=int(category_id) if category_id else None,
            file=uploaded_file,
            file_size=uploaded_file.size,
            is_published=request.POST.get("is_published") == "on",
            access_level=request.POST.get("access_level", "PUBLIC"),
            uploaded_by=request.user,
        )
        doc.save()
        messages.success(request, f"Document '{doc.title}' uploaded.")
        return redirect("admin_panel:documents_list")

    categories = DocumentCategory.objects.all()
    return render(request, "admin_panel/document_upload.html", {"categories": categories})


@permission_required("documents.manage")
def document_delete(request, pk):
    if request.method == "POST":
        doc = get_object_or_404(Document, pk=pk)
        title = doc.title
        doc.file.delete(save=False)
        doc.delete()
        messages.success(request, f"Document '{title}' deleted.")
    return redirect("admin_panel:documents_list")


@permission_required("documents.manage")
def document_categories(request):
    if request.method == "POST":
        from django.utils.text import slugify
        name = request.POST.get("name", "").strip()
        if name:
            slug = slugify(name)
            if not DocumentCategory.objects.filter(slug=slug).exists():
                DocumentCategory.objects.create(
                    name=name,
                    slug=slug,
                    description=request.POST.get("description", ""),
                    display_order=int(request.POST.get("display_order", 0)),
                )
                messages.success(request, f"Category '{name}' created.")
            else:
                messages.error(request, f"A category with slug '{slug}' already exists.")
        return redirect("admin_panel:document_categories")

    categories = DocumentCategory.objects.all()
    return render(request, "admin_panel/document_categories.html", {"categories": categories})


# --- Event Roster Builder ---

@permission_required("events.manage_roster")
def event_roster(request, pk):
    event = get_object_or_404(Event, pk=pk)
    roster_groups = event.get_roster_groups()
    available = event.availability.select_related("controller").prefetch_related("preferred_positions")
    all_positions = Position.objects.all()

    if request.method == "POST":
        from django.utils.dateparse import parse_datetime as pd
        for ep in event.positions.all():
            controller_id = request.POST.get(f"assign_{ep.pk}")
            start = pd(request.POST.get(f"start_{ep.pk}", "") or "")
            end = pd(request.POST.get(f"end_{ep.pk}", "") or "")
            if controller_id:
                ep.assigned_controller_id = int(controller_id)
                ep.is_filled = True
            else:
                ep.assigned_controller = None
                ep.is_filled = False
            ep.start_time = start
            ep.end_time = end
            ep.save()
        messages.success(request, "Roster assignments saved.")
        return redirect("admin_panel:event_roster", pk=pk)

    # Build available controllers list
    available_controllers = []
    for av in available:
        user = av.controller
        preferred = list(av.preferred_positions.values_list("callsign", flat=True))
        available_controllers.append({
            "user": user,
            "notes": av.notes,
            "preferred": preferred,
            "rating": user.rating,
            "rating_label": settings.VATSIM_RATINGS.get(user.rating, str(user.rating)),
            "available_from": av.available_from,
            "available_to": av.available_to,
        })

    # Build timeline data for the graphical roster view
    event_start = event.start_datetime
    event_end = event.end_datetime
    total_seconds = max((event_end - event_start).total_seconds(), 1)

    timeline_positions = []
    for group in roster_groups:
        for ep in group["positions"]:
            ep_start = ep.effective_start
            ep_end = ep.effective_end
            left_pct = max(0, (ep_start - event_start).total_seconds() / total_seconds * 100)
            width_pct = max(1, (ep_end - ep_start).total_seconds() / total_seconds * 100)
            timeline_positions.append({
                "ep": ep,
                "group_color": group["color_bg"],
                "left_pct": round(left_pct, 2),
                "width_pct": round(min(width_pct, 100 - left_pct), 2),
            })

    # Build hour markers
    from datetime import timedelta
    hour_markers = []
    current = event_start.replace(minute=0, second=0, microsecond=0)
    if current < event_start:
        current += timedelta(hours=1)
    while current <= event_end:
        pct = (current - event_start).total_seconds() / total_seconds * 100
        hour_markers.append({"time": current, "pct": round(pct, 2)})
        current += timedelta(hours=1)

    return render(request, "admin_panel/event_roster.html", {
        "event": event,
        "roster_groups": roster_groups,
        "available_controllers": available_controllers,
        "all_positions": all_positions,
        "vatsim_ratings": settings.VATSIM_RATINGS,
        "timeline_positions": timeline_positions,
        "hour_markers": hour_markers,
    })


@permission_required("events.manage_roster")
def event_add_position(request, pk):
    if request.method == "POST":
        from django.utils.dateparse import parse_datetime as pd
        event = get_object_or_404(Event, pk=pk)
        position_id = request.POST.get("position_id")
        start = pd(request.POST.get("start_time", "") or "")
        end = pd(request.POST.get("end_time", "") or "")
        if position_id:
            position = get_object_or_404(Position, pk=int(position_id))
            EventPosition.objects.create(
                event=event, position=position,
                start_time=start,
                end_time=end,
            )
            messages.success(request, f"Position '{position.callsign}' added to roster.")
    return redirect("admin_panel:event_roster", pk=pk)


@permission_required("events.manage_roster")
def event_remove_position(request, pk, position_pk):
    if request.method == "POST":
        ep = get_object_or_404(EventPosition, pk=position_pk, event_id=pk)
        ep.delete()
        messages.success(request, "Position removed from roster.")
    return redirect("admin_panel:event_roster", pk=pk)


@permission_required("events.manage_roster")
def event_publish_roster(request, pk):
    if request.method == "POST":
        event = get_object_or_404(Event, pk=pk)
        action = request.POST.get("action", "publish")

        if action == "publish":
            event.roster_published = True
            event.save()
            messages.success(request, f"Roster for '{event.title}' is now visible to controllers.")
        elif action == "unpublish":
            event.roster_published = False
            event.roster_public = False
            event.save()
            messages.success(request, f"Roster for '{event.title}' has been unpublished.")
        elif action == "make_public":
            event.roster_public = True
            event.save()
            messages.success(request, f"Roster for '{event.title}' is now publicly visible.")
        elif action == "make_private":
            event.roster_public = False
            event.save()
            messages.success(request, f"Roster for '{event.title}' is now visible to controllers only.")

    return redirect("admin_panel:event_roster", pk=pk)


# --- Positions Management ---

@permission_required("controllers.manage")
def positions_list(request):
    positions = Position.objects.select_related("airport").order_by("airport__icao", "callsign")
    return render(request, "admin_panel/positions_list.html", {
        "positions": positions,
        "position_types": PositionType.choices,
    })


@permission_required("controllers.manage")
def position_edit(request, pk=None):
    position = get_object_or_404(Position, pk=pk) if pk else None

    if request.method == "POST":
        callsign = request.POST.get("callsign", "").strip().upper()
        name = request.POST.get("name", "").strip()
        position_type = request.POST.get("position_type", "")
        airport_id = request.POST.get("airport") or None
        frequency = request.POST.get("frequency", "").strip()
        min_rating = int(request.POST.get("min_rating", 1))
        is_home = request.POST.get("is_home") == "on"

        if not callsign:
            messages.error(request, "Callsign is required.")
            return redirect("admin_panel:positions_list")

        if position:
            position.callsign = callsign
            position.name = name
            position.position_type = position_type
            position.airport_id = airport_id
            position.frequency = frequency
            position.min_rating = min_rating
            position.is_home = is_home
            position.save()
            messages.success(request, f"Position '{callsign}' updated.")
        else:
            Position.objects.create(
                callsign=callsign,
                name=name,
                position_type=position_type,
                airport_id=airport_id,
                frequency=frequency,
                min_rating=min_rating,
                is_home=is_home,
            )
            messages.success(request, f"Position '{callsign}' created.")

        return redirect("admin_panel:positions_list")

    return render(request, "admin_panel/position_form.html", {
        "position": position,
        "position_types": PositionType.choices,
        "vatsim_ratings": settings.VATSIM_RATINGS,
        "airports": Airport.objects.all(),
    })


@permission_required("controllers.manage")
def position_delete(request, pk):
    if request.method == "POST":
        position = get_object_or_404(Position, pk=pk)
        callsign = position.callsign
        position.delete()
        messages.success(request, f"Position '{callsign}' deleted.")
    return redirect("admin_panel:positions_list")


# --- Airport Management ---

@permission_required("admin_panel.access")
def airports_list(request):
    airports = Airport.objects.all()
    return render(request, "admin_panel/airports_list.html", {"airports": airports})


@permission_required("admin_panel.access")
def airport_edit(request, pk=None):
    airport = get_object_or_404(Airport, pk=pk) if pk else None

    if request.method == "POST":
        icao = request.POST.get("icao", "").strip().upper()
        if not icao:
            messages.error(request, "ICAO code is required.")
            return redirect("admin_panel:airports_list")

        data = {
            "icao": icao,
            "name": request.POST.get("name", "").strip(),
            "latitude": float(request.POST.get("latitude", 0) or 0),
            "longitude": float(request.POST.get("longitude", 0) or 0),
            "elevation_ft": int(request.POST.get("elevation_ft", 0) or 0),
            "description": request.POST.get("description", ""),
            "staff_notice": request.POST.get("staff_notice", ""),
            "chart_ad_url": request.POST.get("chart_ad_url", "").strip(),
            "chart_sid_url": request.POST.get("chart_sid_url", "").strip(),
            "chart_star_url": request.POST.get("chart_star_url", "").strip(),
            "chart_iap_url": request.POST.get("chart_iap_url", "").strip(),
            "chart_ground_url": request.POST.get("chart_ground_url", "").strip(),
            "chart_extra_urls": request.POST.get("chart_extra_urls", ""),
            "is_visible": request.POST.get("is_visible") == "on",
            "show_metar_on_homepage": request.POST.get("show_metar_on_homepage") == "on",
            "display_order": int(request.POST.get("display_order", 0) or 0),
        }

        if airport:
            for k, v in data.items():
                setattr(airport, k, v)
            airport.save()
            messages.success(request, f"Airport '{icao}' updated.")
        else:
            airport = Airport.objects.create(**data)
            messages.success(request, f"Airport '{icao}' created.")

        return redirect("admin_panel:airports_list")

    return render(request, "admin_panel/airport_form.html", {"airport": airport})


@permission_required("admin_panel.access")
def airport_runways(request, pk):
    """Handle all runway operations separately from airport data."""
    airport = get_object_or_404(Airport, pk=pk)

    if request.method == "POST":
        action = request.POST.get("runway_action")

        if action == "add":
            designator = request.POST.get("rwy_designator", "").strip().upper()
            heading = int(request.POST.get("rwy_heading", 0) or 0)
            length_m = int(request.POST.get("rwy_length_m", 0) or 0)
            pref_arr = request.POST.get("rwy_pref_arrival") == "on"
            pref_dep = request.POST.get("rwy_pref_departure") == "on"
            max_tw = int(request.POST.get("rwy_max_tailwind", 5) or 5)
            if designator:
                Runway.objects.get_or_create(
                    airport=airport, designator=designator,
                    defaults={
                        "heading": heading,
                        "length_m": length_m,
                        "preferential_arrival": pref_arr,
                        "preferential_departure": pref_dep,
                        "max_tailwind_kt": max_tw,
                    },
                )
                messages.success(request, f"Runway {designator} added.")

        elif action == "update":
            for rwy in airport.runways.all():
                prefix = f"rwy_{rwy.pk}_"
                if f"{prefix}designator" in request.POST:
                    rwy.designator = request.POST.get(f"{prefix}designator", "").strip().upper()
                    rwy.heading = int(request.POST.get(f"{prefix}heading", 0) or 0)
                    rwy.length_m = int(request.POST.get(f"{prefix}length_m", 0) or 0)
                    rwy.preferential_arrival = request.POST.get(f"{prefix}pref_arrival") == "on"
                    rwy.preferential_departure = request.POST.get(f"{prefix}pref_departure") == "on"
                    rwy.max_tailwind_kt = int(request.POST.get(f"{prefix}max_tailwind", 5) or 5)
                    rwy.save()
            messages.success(request, "Runways updated.")

        elif action == "delete":
            rwy_pk = request.POST.get("rwy_pk")
            if rwy_pk:
                Runway.objects.filter(pk=rwy_pk, airport=airport).delete()
                messages.success(request, "Runway removed.")

    return redirect("admin_panel:airport_edit", pk=pk)


@permission_required("admin_panel.access")
def airport_delete(request, pk):
    if request.method == "POST":
        airport = get_object_or_404(Airport, pk=pk)
        icao = airport.icao
        airport.delete()
        messages.success(request, f"Airport '{icao}' deleted.")
    return redirect("admin_panel:airports_list")


# --- Discord Media Library ---

@permission_required("admin_panel.access")
def discord_media(request):
    from apps.notifications.models import MediaUpload
    uploads = MediaUpload.objects.all()[:50]
    return render(request, "admin_panel/discord_media.html", {"uploads": uploads})


@permission_required("admin_panel.access")
def discord_media_upload(request):
    if request.method != "POST":
        return redirect("admin_panel:discord_media")

    from apps.notifications.models import MediaUpload

    file = request.FILES.get("file")
    if not file:
        messages.error(request, "No file selected.")
        return redirect("admin_panel:discord_media")

    title = request.POST.get("title", "").strip() or file.name

    upload = MediaUpload.objects.create(
        title=title,
        file=file,
        file_size=file.size,
        content_type=file.content_type or "",
        uploaded_by=request.user,
    )

    DiscordBotLog.objects.create(
        action="MEDIA_UPLOAD",
        detail=f"Uploaded {title} ({upload.file_size_display})",
        performed_by=request.user,
    )
    messages.success(request, f"Uploaded '{title}'. URL: {upload.url}")
    return redirect("admin_panel:discord_media")


@permission_required("admin_panel.access")
def discord_media_delete(request, pk):
    if request.method != "POST":
        return redirect("admin_panel:discord_media")

    from apps.notifications.models import MediaUpload
    upload = get_object_or_404(MediaUpload, pk=pk)
    name = upload.title
    upload.file.delete(save=False)
    upload.delete()
    messages.success(request, f"Deleted '{name}'.")
    return redirect("admin_panel:discord_media")


# --- Discord Control Centre ---

@permission_required("admin_panel.site_config")
def discord_control_centre(request):
    from apps.notifications.discord import get_bot_user, get_guild_info, get_guild_channels

    config = SiteConfig.get()
    guild_id = config.discord_guild_id if config else ""

    bot_user = get_bot_user()
    guild_info = get_guild_info(guild_id) if guild_id else None
    channels = get_guild_channels(guild_id) if guild_id else []
    recent_logs = DiscordBotLog.objects.select_related("performed_by")[:20]

    return render(request, "admin_panel/discord_control_centre.html", {
        "bot_user": bot_user,
        "guild_info": guild_info,
        "channels": channels,
        "recent_logs": recent_logs,
        "config": config,
    })


@permission_required("admin_panel.site_config")
def discord_change_nickname(request):
    if request.method != "POST":
        return redirect("admin_panel:discord_control_centre")

    from apps.notifications.discord import change_bot_nickname

    config = SiteConfig.get()
    nickname = request.POST.get("nickname", "").strip()

    if not nickname:
        messages.error(request, "Nickname cannot be empty.")
        return redirect("admin_panel:discord_control_centre")

    success = change_bot_nickname(config.discord_guild_id, nickname)
    if success:
        DiscordBotLog.objects.create(
            action="NICKNAME_CHANGE",
            detail=f"Bot nickname changed to '{nickname}'",
            performed_by=request.user,
        )
        messages.success(request, f"Bot nickname changed to '{nickname}'.")
    else:
        messages.error(request, "Failed to change bot nickname. Check bot permissions.")

    return redirect("admin_panel:discord_control_centre")


@permission_required("admin_panel.site_config")
def discord_send_test(request):
    if request.method != "POST":
        return redirect("admin_panel:discord_control_centre")

    from apps.notifications.discord import send_channel_message, _embed

    channel_id = request.POST.get("channel_id", "")
    if not channel_id:
        messages.error(request, "Please select a channel.")
        return redirect("admin_panel:discord_control_centre")

    embed = _embed(
        "Test Message",
        "This is a test message sent from the VATéir Discord Control Centre.",
        footer="Discord Control Centre Test",
        timestamp=True,
    )
    msg_id = send_channel_message(channel_id, embed=embed)
    if msg_id:
        DiscordBotLog.objects.create(
            action="TEST_MESSAGE",
            detail=f"Test message sent to channel {channel_id}",
            performed_by=request.user,
        )
        messages.success(request, "Test message sent successfully.")
    else:
        messages.error(request, "Failed to send test message. Check bot permissions and channel ID.")

    return redirect("admin_panel:discord_control_centre")


@permission_required("admin_panel.site_config")
def discord_announce(request):
    from apps.notifications.discord import get_guild_channels, build_announcement_embed, send_channel_message
    from apps.notifications.models import AnnouncementType

    config = SiteConfig.get()
    guild_id = config.discord_guild_id if config else ""
    channels = get_guild_channels(guild_id) if guild_id else []

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        body = request.POST.get("body", "").strip()
        channel_id = request.POST.get("channel_id", "")
        embed_color = request.POST.get("embed_color", "#059669")
        banner_image_url = request.POST.get("banner_image_url", "").strip()
        media_url = request.POST.get("media_url", "").strip()
        announcement_type = request.POST.get("announcement_type", "GENERAL")

        if not title or not body or not channel_id:
            messages.error(request, "Title, body and channel are required.")
            return render(request, "admin_panel/discord_announce.html", {
                "channels": channels,
                "announcement_types": AnnouncementType.choices,
                "form_data": request.POST,
            })

        embed = build_announcement_embed(title, body, embed_color, banner_image_url, announcement_type)
        # Send media URL as plain content so Discord auto-previews it alongside the embed
        content = media_url if media_url else ""
        msg_id = send_channel_message(channel_id, content, embed)

        if msg_id:
            # Find channel name for the record
            channel_name = ""
            for ch in channels:
                if ch["id"] == channel_id:
                    channel_name = ch["name"]
                    break

            DiscordAnnouncement.objects.create(
                title=title,
                body=body,
                channel_id=channel_id,
                channel_name=channel_name,
                embed_color=embed_color,
                banner_image_url=banner_image_url,
                announcement_type=announcement_type,
                sent_by=request.user,
                discord_message_id=msg_id,
            )
            DiscordBotLog.objects.create(
                action="ANNOUNCEMENT",
                detail=f"Announcement '{title}' sent to #{channel_name or channel_id}",
                performed_by=request.user,
            )
            messages.success(request, f"Announcement '{title}' posted successfully.")
            return redirect("admin_panel:discord_control_centre")
        else:
            messages.error(request, "Failed to send announcement. Check bot permissions.")
            return render(request, "admin_panel/discord_announce.html", {
                "channels": channels,
                "announcement_types": AnnouncementType.choices,
                "form_data": request.POST,
            })

    from apps.notifications.models import MediaUpload
    media_library = MediaUpload.objects.all()[:30]

    return render(request, "admin_panel/discord_announce.html", {
        "channels": channels,
        "announcement_types": AnnouncementType.choices,
        "media_library": media_library,
        "form_data": {},
    })


@permission_required("admin_panel.site_config")
def discord_bans(request):
    active_bans = DiscordBan.objects.filter(is_active=True).select_related("banned_by", "user")
    past_bans = DiscordBan.objects.filter(is_active=False).select_related("banned_by", "unbanned_by", "user")

    config = SiteConfig.get()
    guild_id = config.discord_guild_id if config else ""

    return render(request, "admin_panel/discord_bans.html", {
        "active_bans": active_bans,
        "past_bans": past_bans,
        "guild_id": guild_id,
    })


@permission_required("admin_panel.site_config")
def discord_ban_user(request):
    if request.method != "POST":
        return redirect("admin_panel:discord_bans")

    from apps.notifications.discord import ban_guild_member, notify_user_banned

    config = SiteConfig.get()
    guild_id = config.discord_guild_id if config else ""

    discord_user_id = request.POST.get("discord_user_id", "").strip()
    reason = request.POST.get("reason", "").strip()
    also_site_ban = request.POST.get("also_site_ban") == "on"

    if not discord_user_id or not reason:
        messages.error(request, "Discord User ID and reason are required.")
        return redirect("admin_panel:discord_bans")

    success = ban_guild_member(guild_id, discord_user_id, reason)
    if success:
        # Optionally deactivate linked site user
        linked_user = User.objects.filter(discord_user_id=discord_user_id).first()
        if also_site_ban and linked_user:
            linked_user.is_active = False
            linked_user.save()

        ban = DiscordBan.objects.create(
            user=linked_user,
            discord_user_id=discord_user_id,
            discord_username=linked_user.vatsim_name if linked_user else "",
            reason=reason,
            banned_by=request.user,
            is_active=True,
            also_site_banned=also_site_ban,
            guild_id=guild_id,
        )
        DiscordBotLog.objects.create(
            action="BAN_USER",
            detail=f"Banned Discord user {discord_user_id}. Reason: {reason}",
            performed_by=request.user,
        )
        notify_user_banned(
            ban.discord_username or discord_user_id,
            reason,
            request.user.vatsim_name or str(request.user),
        )
        messages.success(request, f"User {discord_user_id} has been banned.")
    else:
        messages.error(request, "Failed to ban user. Check bot permissions and the user ID.")

    return redirect("admin_panel:discord_bans")


@permission_required("admin_panel.site_config")
def discord_unban_user(request, pk):
    if request.method != "POST":
        return redirect("admin_panel:discord_bans")

    from apps.notifications.discord import unban_guild_member

    ban = get_object_or_404(DiscordBan, pk=pk, is_active=True)

    success = unban_guild_member(ban.guild_id, ban.discord_user_id)
    if success:
        ban.is_active = False
        ban.unbanned_at = timezone.now()
        ban.unbanned_by = request.user
        ban.save()

        # Optionally reactivate linked site user
        if ban.also_site_banned and ban.user:
            ban.user.is_active = True
            ban.user.save()

        DiscordBotLog.objects.create(
            action="UNBAN_USER",
            detail=f"Unbanned Discord user {ban.discord_user_id} ({ban.discord_username})",
            performed_by=request.user,
        )
        messages.success(request, f"User {ban.discord_username or ban.discord_user_id} has been unbanned.")
    else:
        messages.error(request, "Failed to unban user. Check bot permissions.")

    return redirect("admin_panel:discord_bans")


@permission_required("admin_panel.site_config")
def discord_member_lookup(request):
    """Look up a Discord guild member by ID or search by name."""
    from apps.notifications.discord import get_guild_member, search_guild_members, get_guild_roles

    config = SiteConfig.get()
    guild_id = config.discord_guild_id if config else ""
    member = None
    search_results = []
    roles = []
    query = request.GET.get("q", "").strip()
    user_id = request.GET.get("user_id", "").strip()

    if guild_id:
        roles = get_guild_roles(guild_id)

    if user_id and guild_id:
        member = get_guild_member(guild_id, user_id)
    elif query and guild_id:
        search_results = search_guild_members(guild_id, query, limit=20)

    # Build role name map
    role_map = {r["id"]: r for r in roles}

    return render(request, "admin_panel/discord_member_lookup.html", {
        "query": query,
        "user_id": user_id,
        "member": member,
        "search_results": search_results,
        "role_map": role_map,
        "roles": roles,
        "guild_id": guild_id,
    })


@permission_required("admin_panel.site_config")
def discord_kick_user(request):
    """Kick a member from the Discord guild."""
    if request.method != "POST":
        return redirect("admin_panel:discord_member_lookup")

    from apps.notifications.discord import kick_guild_member

    config = SiteConfig.get()
    guild_id = config.discord_guild_id if config else ""
    user_id = request.POST.get("user_id", "")
    reason = request.POST.get("reason", "Kicked via VATéir admin panel")

    if guild_id and user_id:
        success = kick_guild_member(guild_id, user_id, reason)
        if success:
            DiscordBotLog.objects.create(
                action="KICK_USER",
                detail=f"Kicked Discord user {user_id}. Reason: {reason}",
                performed_by=request.user,
            )
            messages.success(request, f"User {user_id} has been kicked.")
        else:
            messages.error(request, "Failed to kick user. Check bot permissions.")
    else:
        messages.error(request, "Missing guild ID or user ID.")

    return redirect("admin_panel:discord_member_lookup")


@permission_required("admin_panel.site_config")
def discord_manage_role(request):
    """Add or remove a role from a guild member."""
    if request.method != "POST":
        return redirect("admin_panel:discord_member_lookup")

    from apps.notifications.discord import add_member_role, remove_member_role

    config = SiteConfig.get()
    guild_id = config.discord_guild_id if config else ""
    user_id = request.POST.get("user_id", "")
    role_id = request.POST.get("role_id", "")
    action = request.POST.get("action", "add")

    if guild_id and user_id and role_id:
        if action == "add":
            success = add_member_role(guild_id, user_id, role_id)
            verb = "added to"
        else:
            success = remove_member_role(guild_id, user_id, role_id)
            verb = "removed from"

        if success:
            DiscordBotLog.objects.create(
                action="ROLE_CHANGE",
                detail=f"Role {role_id} {verb} user {user_id}",
                performed_by=request.user,
            )
            messages.success(request, f"Role {verb} user successfully.")
        else:
            messages.error(request, f"Failed to modify role. Check bot permissions.")
    else:
        messages.error(request, "Missing required fields.")

    return redirect(f"{request.META.get('HTTP_REFERER', '/admin-panel/discord/members/')}")


@permission_required("admin_panel.site_config")
def discord_send_dm(request):
    """Send a DM to a Discord user via the bot."""
    if request.method != "POST":
        return redirect("admin_panel:discord_control_centre")

    from apps.notifications.discord import send_dm, _embed

    user_id = request.POST.get("user_id", "")
    message_text = request.POST.get("message", "").strip()

    if user_id and message_text:
        embed = _embed("Message from VATéir", message_text, timestamp=True)
        success = send_dm(user_id, "", embed)
        if success:
            DiscordBotLog.objects.create(
                action="SEND_DM",
                detail=f"DM sent to {user_id}: {message_text[:100]}",
                performed_by=request.user,
            )
            messages.success(request, f"DM sent to user {user_id}.")
        else:
            messages.error(request, "Failed to send DM. User may have DMs disabled or is not in a shared server.")
    else:
        messages.error(request, "User ID and message are required.")

    return redirect(request.META.get("HTTP_REFERER", "/admin-panel/discord/"))


@permission_required("admin_panel.site_config")
def discord_send_message(request):
    """Send a custom message to a channel."""
    if request.method != "POST":
        return redirect("admin_panel:discord_control_centre")

    from apps.notifications.discord import send_channel_message, _embed

    channel_id = request.POST.get("channel_id", "")
    message_text = request.POST.get("message", "").strip()
    media_url = request.POST.get("media_url", "").strip()
    send_raw = request.POST.get("raw") == "1"

    if channel_id and message_text:
        if send_raw:
            msg_id = send_channel_message(channel_id, message_text)
        else:
            embed = _embed("VATéir", message_text, timestamp=True)
            # If a media URL is provided, send it as plain content alongside the embed
            # so Discord auto-embeds the video/image preview
            content = media_url if media_url else ""
            msg_id = send_channel_message(channel_id, content, embed)
        if msg_id:
            DiscordBotLog.objects.create(
                action="SEND_RAW" if send_raw else "SEND_MESSAGE",
                detail=f"{'Raw' if send_raw else 'Embed'} message to {channel_id}: {message_text[:100]}",
                performed_by=request.user,
            )
            messages.success(request, "Message sent.")
        else:
            messages.error(request, "Failed to send message.")
    else:
        messages.error(request, "Channel and message are required.")

    return redirect("admin_panel:discord_control_centre")


@permission_required("admin_panel.site_config")
def discord_member_search_api(request):
    """JSON API for searching Discord members (used by Tom Select)."""
    from django.http import JsonResponse
    from apps.notifications.discord import search_guild_members

    config = SiteConfig.get()
    guild_id = config.discord_guild_id if config else ""
    query = request.GET.get("q", "").strip()

    if not query or len(query) < 2 or not guild_id:
        return JsonResponse([], safe=False)

    members = search_guild_members(guild_id, query, limit=10)
    results = []
    for m in members:
        user = m.get("user", {})
        results.append({
            "id": user.get("id", ""),
            "username": user.get("username", ""),
            "display_name": m.get("nick") or user.get("global_name") or user.get("username", ""),
            "avatar": user.get("avatar", ""),
        })
    return JsonResponse(results, safe=False)


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


@permission_required("admin_panel.site_config")
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


@permission_required("admin_panel.site_config")
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


@permission_required("admin_panel.site_config")
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


# --- VATSIM Member Lookup ---

@permission_required("controllers.manage")
def vatsim_member_lookup(request):
    """Query the VATSIM API by CID and display member info."""
    cid = request.GET.get("cid", "").strip()
    member = None
    stats = None
    error = None
    local_controller = None
    flags = {}

    if cid:
        if not cid.isdigit():
            error = "CID must be a number."
        else:
            import requests as http_requests

            # Fetch member info
            try:
                resp = http_requests.get(
                    f"{settings.VATSIM_API_BASE}/members/{cid}",
                    timeout=10,
                )
                resp.raise_for_status()
                member = resp.json()
            except http_requests.exceptions.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    error = f"No VATSIM member found with CID {cid}."
                else:
                    error = f"VATSIM API error: {exc}"
            except Exception as exc:
                error = f"Could not reach VATSIM API: {exc}"

            # Fetch stats
            if member:
                try:
                    resp = http_requests.get(
                        f"{settings.VATSIM_API_BASE}/members/{cid}/stats",
                        timeout=10,
                    )
                    resp.raise_for_status()
                    stats = resp.json()
                except Exception:
                    pass  # stats are optional

            # Derive flags
            if member:
                subdivision = getattr(settings, "VATSIM_SUBDIVISION", "IRL")
                member_sub = member.get("subdivision_id", "")
                member_div = member.get("division_id", "")
                member_region = member.get("region_id", "")
                flags["is_home"] = (
                    member_sub == subdivision
                    and member_div == "EUD"
                    and member_region == "EMEA"
                )
                flags["is_same_division"] = member_div == "EUD"
                flags["is_same_region"] = member_region == "EMEA"
                flags["rating_label"] = settings.VATSIM_RATINGS.get(
                    member.get("rating", 0), str(member.get("rating", "?"))
                )
                flags["pilot_rating_label"] = {
                    0: "None", 1: "PPL", 3: "IR", 7: "CMEL",
                    15: "ATPL", 31: "FI", 63: "FE",
                }.get(member.get("pilotrating", 0), str(member.get("pilotrating", 0)))
                flags["military_rating_label"] = {
                    0: "None", 1: "M1", 3: "M2", 7: "M3", 15: "M4",
                }.get(member.get("militaryrating", 0), str(member.get("militaryrating", 0)))

                # Check local database
                try:
                    local_controller = Controller.objects.get(cid=int(cid))
                except Controller.DoesNotExist:
                    pass

    return render(request, "admin_panel/vatsim_member_lookup.html", {
        "cid": cid,
        "member": member,
        "stats": stats,
        "error": error,
        "flags": flags,
        "local_controller": local_controller,
    })
