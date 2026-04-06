import json

from django.db import models
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import permission_required
from .models import (
    TrainingRequest, TrainingRequestStatus, TrainingSession, SessionStatus,
    TrainingNote, TrainingCourse, SessionReport, CompetencyRating,
    StudentTaskProgress, TrainingCompetency, TrainingAvailability,
)


# ─── Student Views ────────────────────────────────────────────────

@login_required
def my_training(request):
    training_requests = TrainingRequest.objects.filter(student=request.user)
    return render(request, "training/my_training.html", {"training_requests": training_requests})


@login_required
def request_training(request):
    courses = TrainingCourse.objects.filter(is_active=True)

    if request.method == "POST":
        course_id = request.POST.get("course")
        notes = request.POST.get("notes", "")

        course = get_object_or_404(TrainingCourse, pk=course_id, is_active=True)

        # Check for existing active request on this course
        existing = TrainingRequest.objects.filter(
            student=request.user,
            course=course,
            status__in=[TrainingRequestStatus.WAITING, TrainingRequestStatus.ACCEPTED, TrainingRequestStatus.IN_PROGRESS],
        ).exists()
        if existing:
            messages.error(request, "You already have an active request for this course.")
            return redirect("training:my_training")

        # Assign position at end of waiting list
        max_pos = TrainingRequest.objects.filter(
            course=course, status=TrainingRequestStatus.WAITING
        ).aggregate(models.Max("position"))["position__max"] or 0

        TrainingRequest.objects.create(
            student=request.user,
            course=course,
            requested_rating=course.to_rating,
            position=max_pos + 1,
            notes=notes,
        )
        messages.success(request, "Training request submitted. You have been added to the waiting list.")
        return redirect("training:my_training")

    return render(request, "training/request_training.html", {"courses": courses})


@login_required
def training_detail(request, pk):
    tr = get_object_or_404(TrainingRequest, pk=pk)

    # Access control: student, mentors of their sessions, or staff
    is_own = tr.student == request.user
    is_mentor_of = tr.sessions.filter(mentor=request.user).exists()
    is_staff = request.user.has_permission("training.mentor") or request.user.has_permission("training.manage") or request.user.is_superuser

    if not (is_own or is_mentor_of or is_staff):
        return redirect("training:my_training")

    sessions = tr.sessions.select_related("mentor", "report").order_by("-session_date")
    notes = tr.training_notes.all()
    if not is_staff:
        notes = notes.filter(is_internal=False)

    # Task progress
    task_progress = []
    if tr.course:
        for task_def in tr.course.task_definitions.all():
            progress = tr.task_progress.filter(task=task_def).first()
            task_progress.append({
                "task": task_def,
                "completed": progress.is_completed if progress else False,
                "session": progress.completed_by_session if progress else None,
            })

    return render(request, "training/detail.html", {
        "training_request": tr,
        "sessions": sessions,
        "notes": notes,
        "task_progress": task_progress,
        "is_staff": is_staff,
        "is_own": is_own,
    })


@login_required
def view_report(request, session_pk):
    """Student or mentor views a published session report."""
    session = get_object_or_404(TrainingSession, pk=session_pk)
    report = get_object_or_404(SessionReport, session=session)

    # Access: student of the request, the session mentor, or staff
    is_own = session.training_request.student == request.user
    is_mentor = session.mentor == request.user
    is_staff = request.user.has_permission("training.mentor") or request.user.has_permission("training.manage") or request.user.is_superuser

    if not (is_own or is_mentor or is_staff):
        return redirect("training:my_training")

    # Students can only see published reports
    if is_own and not is_staff and not is_mentor and not report.is_published:
        messages.info(request, "This report has not been published yet.")
        return redirect("training:detail", pk=session.training_request.pk)

    ratings = report.ratings.select_related("competency").order_by("competency__display_order")

    return render(request, "training/view_report.html", {
        "session": session,
        "report": report,
        "ratings": ratings,
    })


# ─── Mentor Views ─────────────────────────────────────────────────

@permission_required("training.mentor")
def mentor_dashboard(request):
    all_sessions = TrainingSession.objects.filter(
        mentor=request.user,
    ).select_related("student", "training_request__course").order_by("-session_date")

    # Upcoming scheduled sessions
    upcoming = all_sessions.filter(
        status=SessionStatus.SCHEDULED, session_date__gte=timezone.now()
    )

    # Outstanding reports: completed sessions with no report or unpublished report
    completed_no_report = all_sessions.filter(
        status=SessionStatus.COMPLETED,
    ).exclude(report__isnull=False)

    unpublished_reports = all_sessions.filter(
        status=SessionStatus.COMPLETED,
        report__isnull=False,
        report__is_published=False,
    )

    outstanding_reports = (completed_no_report | unpublished_reports).distinct()

    # My active students (unique training requests I have sessions for that are in progress)
    active_student_ids = all_sessions.filter(
        training_request__status__in=[
            TrainingRequestStatus.ACCEPTED,
            TrainingRequestStatus.IN_PROGRESS,
        ]
    ).values_list("training_request_id", flat=True).distinct()
    active_students = TrainingRequest.objects.filter(
        pk__in=active_student_ids
    ).select_related("student", "course")

    # Recent past sessions
    past = all_sessions.filter(
        status__in=[SessionStatus.COMPLETED, SessionStatus.CANCELLED, SessionStatus.NO_SHOW]
    )[:15]

    # Stats
    total_sessions = all_sessions.count()
    total_completed = all_sessions.filter(status=SessionStatus.COMPLETED).count()
    total_hours = sum(s.duration_minutes for s in all_sessions.filter(status=SessionStatus.COMPLETED)) / 60

    # Available students (unbooked availability windows from today onwards)
    available_students = TrainingAvailability.objects.filter(
        is_booked=False,
        date__gte=timezone.now().date(),
    ).select_related("student").order_by("date", "start_time")

    return render(request, "training/mentor_dashboard.html", {
        "upcoming_sessions": upcoming,
        "outstanding_reports": outstanding_reports,
        "active_students": active_students,
        "past_sessions": past,
        "total_sessions": total_sessions,
        "total_completed": total_completed,
        "total_hours": round(total_hours, 1),
        "outstanding_count": outstanding_reports.count(),
        "available_students": available_students,
    })


@permission_required("training.mentor")
def log_session(request, pk):
    tr = get_object_or_404(TrainingRequest, pk=pk)

    if request.method == "POST":
        session = TrainingSession.objects.create(
            training_request=tr,
            student=tr.student,
            mentor=request.user,
            session_date=request.POST.get("session_date"),
            duration_minutes=int(request.POST.get("duration_minutes", 0)),
            session_type=request.POST.get("session_type", "PRACTICAL"),
            status=request.POST.get("status", "SCHEDULED"),
            notes=request.POST.get("notes", ""),
            passed=request.POST.get("passed") if request.POST.get("passed") else None,
        )
        messages.success(request, "Training session logged.")

        # If completed, redirect to report
        if session.status == SessionStatus.COMPLETED:
            return redirect("training:write_report", session_pk=session.pk)

        return redirect("training:detail", pk=pk)

    return render(request, "training/log_session.html", {"training_request": tr})


@permission_required("training.mentor")
def write_report(request, session_pk):
    """Mentor writes or edits a session report with competency ratings."""
    session = get_object_or_404(TrainingSession, pk=session_pk)

    # Only the session mentor or staff can write reports
    if session.mentor != request.user and not request.user.is_superuser:
        if not request.user.has_permission("training.manage"):
            return redirect("training:mentor_dashboard")

    report, _ = SessionReport.objects.get_or_create(session=session)

    # Get competencies for this course
    competencies = []
    course = session.training_request.course
    if course:
        competencies = course.competencies.filter(is_active=True).order_by("display_order")

    if request.method == "POST":
        report.summary = request.POST.get("summary", "")
        report.is_published = request.POST.get("is_published") == "on"
        report.save()

        # Save competency ratings
        for comp in competencies:
            rating_val = request.POST.get(f"rating_{comp.pk}", "0")
            comment = request.POST.get(f"comment_{comp.pk}", "")
            CompetencyRating.objects.update_or_create(
                report=report,
                competency=comp,
                defaults={
                    "rating": int(rating_val),
                    "comment": comment,
                },
            )

        messages.success(request, "Report saved." + (" Published to student." if report.is_published else ""))
        return redirect("training:detail", pk=session.training_request.pk)

    # Load existing ratings
    existing_ratings = {r.competency_id: r for r in report.ratings.all()}
    comp_data = []
    for comp in competencies:
        existing = existing_ratings.get(comp.pk)
        comp_data.append({
            "competency": comp,
            "rating": existing.rating if existing else 0,
            "comment": existing.comment if existing else "",
        })

    return render(request, "training/write_report.html", {
        "session": session,
        "report": report,
        "comp_data": comp_data,
    })


# ─── Staff/Admin Training Board ──────────────────────────────────

@permission_required("training.manage")
def training_board(request):
    """Trello-style kanban board for training management."""
    courses = TrainingCourse.objects.filter(is_active=True)
    active_course_id = request.GET.get("course")

    if active_course_id:
        active_course = get_object_or_404(TrainingCourse, pk=active_course_id)
    elif courses.exists():
        active_course = courses.first()
    else:
        active_course = None

    columns = []
    if active_course:
        for status_value, status_label in TrainingRequestStatus.choices:
            requests = TrainingRequest.objects.filter(
                course=active_course,
                status=status_value,
            ).select_related("student").order_by("position", "created_at")

            # Annotate with task progress
            cards = []
            for tr in requests:
                cards.append({
                    "request": tr,
                    "task_pct": tr.task_completion_pct,
                    "session_count": tr.sessions.count(),
                })

            columns.append({
                "status": status_value,
                "label": status_label,
                "cards": cards,
                "count": len(cards),
            })

    return render(request, "training/board.html", {
        "courses": courses,
        "active_course": active_course,
        "columns": columns,
    })


@permission_required("training.manage")
@require_POST
def board_move_card(request):
    """AJAX endpoint to move a student card between swimlanes."""
    try:
        data = json.loads(request.body)
        request_id = data.get("request_id")
        new_status = data.get("status")
        new_position = data.get("position", 0)

        tr = TrainingRequest.objects.get(pk=request_id)
        tr.status = new_status
        tr.position = new_position
        tr.save(update_fields=["status", "position", "updated_at"])

        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


# ─── Waiting List Management (staff) ─────────────────────────────

@permission_required("training.manage")
def waiting_list(request):
    """Manage the waiting list — reorder and remove."""
    courses = TrainingCourse.objects.filter(is_active=True)
    active_course_id = request.GET.get("course")

    if active_course_id:
        active_course = get_object_or_404(TrainingCourse, pk=active_course_id)
    elif courses.exists():
        active_course = courses.first()
    else:
        active_course = None

    waiting = []
    if active_course:
        waiting = TrainingRequest.objects.filter(
            course=active_course,
            status=TrainingRequestStatus.WAITING,
        ).select_related("student").order_by("position", "created_at")

    return render(request, "training/waiting_list.html", {
        "courses": courses,
        "active_course": active_course,
        "waiting": waiting,
    })


@permission_required("training.manage")
@require_POST
def reorder_waiting_list(request):
    """AJAX endpoint to reorder the waiting list."""
    try:
        data = json.loads(request.body)
        order = data.get("order", [])
        for idx, request_id in enumerate(order):
            TrainingRequest.objects.filter(pk=request_id).update(position=idx + 1)
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


@permission_required("training.manage")
@require_POST
def remove_from_waiting(request, pk):
    tr = get_object_or_404(TrainingRequest, pk=pk)
    tr.status = TrainingRequestStatus.WITHDRAWN
    tr.save(update_fields=["status", "updated_at"])
    messages.success(request, f"Removed {tr.student} from waiting list.")
    return redirect("training:waiting_list")


@permission_required("training.manage")
@require_POST
def bulk_remove_from_waiting(request):
    """Remove multiple students from the waiting list at once."""
    ids = request.POST.getlist("selected")
    if ids:
        count = TrainingRequest.objects.filter(
            pk__in=ids, status=TrainingRequestStatus.WAITING,
        ).update(status=TrainingRequestStatus.WITHDRAWN)
        messages.success(request, f"Removed {count} student(s) from the waiting list.")
    else:
        messages.warning(request, "No students selected.")
    course_id = request.POST.get("course_id", "")
    url = "training:waiting_list"
    if course_id:
        return redirect(f"{url}?course={course_id}")
    return redirect(url)


# ─── Training Reports (staff) ────────────────────────────────────

@permission_required("training.manage")
def training_reports(request):
    """Reporting dashboard for training staff."""
    # Sessions without reports
    sessions_no_report = TrainingSession.objects.filter(
        status=SessionStatus.COMPLETED,
        report__isnull=True,
    ).select_related("student", "mentor", "training_request__course").order_by("-session_date")[:20]

    # No-show sessions
    no_shows = TrainingSession.objects.filter(
        status=SessionStatus.NO_SHOW,
    ).select_related("student", "mentor").order_by("-session_date")[:20]

    # Cancelled sessions
    cancelled = TrainingSession.objects.filter(
        status=SessionStatus.CANCELLED,
    ).select_related("student", "mentor").order_by("-session_date")[:20]

    # Unpublished reports
    unpublished_reports = SessionReport.objects.filter(
        is_published=False,
    ).select_related("session__student", "session__mentor").order_by("-created_at")[:20]

    # Students waiting longest
    longest_waiting = TrainingRequest.objects.filter(
        status=TrainingRequestStatus.WAITING,
    ).select_related("student", "course").order_by("created_at")[:20]

    # Active students with no sessions in 30 days
    thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
    stale_students = TrainingRequest.objects.filter(
        status__in=[TrainingRequestStatus.ACCEPTED, TrainingRequestStatus.IN_PROGRESS],
    ).exclude(
        sessions__session_date__gte=thirty_days_ago
    ).select_related("student", "course")[:20]

    return render(request, "training/reports.html", {
        "sessions_no_report": sessions_no_report,
        "no_shows": no_shows,
        "cancelled": cancelled,
        "unpublished_reports": unpublished_reports,
        "longest_waiting": longest_waiting,
        "stale_students": stale_students,
    })


# ─── Student Availability ───────────────────────────────────────

@login_required
def post_availability(request):
    """Students post availability windows for mentors to pick up."""
    if request.method == "POST":
        date = request.POST.get("date")
        start_time = request.POST.get("start_time")
        end_time = request.POST.get("end_time")
        notes = request.POST.get("notes", "")

        if date and start_time and end_time:
            # Link to the student's active training request if one exists
            active_tr = TrainingRequest.objects.filter(
                student=request.user,
                status__in=[
                    TrainingRequestStatus.WAITING,
                    TrainingRequestStatus.ACCEPTED,
                    TrainingRequestStatus.IN_PROGRESS,
                ],
            ).first()

            TrainingAvailability.objects.create(
                student=request.user,
                training_request=active_tr,
                date=date,
                start_time=start_time,
                end_time=end_time,
                notes=notes,
            )
            messages.success(request, "Availability posted successfully.")
        else:
            messages.error(request, "Please fill in all required fields.")
        return redirect("training:post_availability")

    upcoming = TrainingAvailability.objects.filter(
        student=request.user,
        date__gte=timezone.now().date(),
    ).order_by("date", "start_time")

    past = TrainingAvailability.objects.filter(
        student=request.user,
        date__lt=timezone.now().date(),
    ).order_by("-date")[:10]

    return render(request, "training/post_availability.html", {
        "upcoming": upcoming,
        "past": past,
    })


@permission_required("training.mentor")
def pick_availability(request, pk):
    """Mentor picks up a student availability slot and creates a 1-hour session."""
    slot = get_object_or_404(
        TrainingAvailability.objects.select_related("student", "training_request"),
        pk=pk,
    )

    if slot.is_booked:
        messages.error(request, "This availability slot has already been booked.")
        return redirect("training:mentor_dashboard")

    if request.method == "POST":
        import datetime
        start_time_str = request.POST.get("start_time")
        if not start_time_str:
            messages.error(request, "Please select a start time.")
            return redirect("training:pick_availability", pk=pk)

        start_time = datetime.time.fromisoformat(start_time_str)

        # Validate start_time is within the availability window
        if start_time < slot.start_time or start_time >= slot.end_time:
            messages.error(request, "Start time must be within the availability window.")
            return redirect("training:pick_availability", pk=pk)

        # Create a 1-hour training session
        session_datetime = datetime.datetime.combine(slot.date, start_time)
        session_datetime = timezone.make_aware(session_datetime) if timezone.is_naive(session_datetime) else session_datetime

        session = TrainingSession.objects.create(
            training_request=slot.training_request,
            is_adhoc=slot.training_request is None,
            student=slot.student,
            mentor=request.user,
            session_date=session_datetime,
            duration_minutes=60,
            session_type="PRACTICAL",
            status=SessionStatus.SCHEDULED,
            notes=f"Picked up from availability slot ({slot.start_time:%H:%M}-{slot.end_time:%H:%M})",
        )

        # Mark the availability as booked
        slot.is_booked = True
        slot.booked_by = request.user
        slot.booked_session = session
        slot.save()

        messages.success(
            request,
            f"Session scheduled with {slot.student.vatsim_name} on {slot.date} at {start_time:%H:%M}z."
        )
        return redirect("training:mentor_dashboard")

    return render(request, "training/pick_availability.html", {
        "slot": slot,
    })
