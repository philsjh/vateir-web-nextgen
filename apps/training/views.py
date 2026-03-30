from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators import mentor_required
from .models import TrainingRequest, TrainingRequestStatus, TrainingSession, TrainingNote


@login_required
def my_training(request):
    training_requests = TrainingRequest.objects.filter(student=request.user)
    return render(request, "training/my_training.html", {"training_requests": training_requests})


@login_required
def request_training(request):
    if request.method == "POST":
        requested_rating = request.POST.get("requested_rating")
        notes = request.POST.get("notes", "")
        if requested_rating:
            TrainingRequest.objects.create(
                student=request.user,
                requested_rating=int(requested_rating),
                notes=notes,
            )
            messages.success(request, "Training request submitted successfully.")
            return redirect("training:my_training")
    return render(request, "training/request_training.html")


@login_required
def training_detail(request, pk):
    tr = get_object_or_404(TrainingRequest, pk=pk)
    # Students can see their own; mentors/staff can see assigned
    if tr.student != request.user and tr.assigned_mentor != request.user:
        user_roles = set(request.user.roles.values_list("role", flat=True))
        from apps.accounts.models import RoleType
        allowed = {RoleType.MENTOR, RoleType.EXAMINER, RoleType.STAFF, RoleType.ADMIN, RoleType.SUPERADMIN}
        if not (user_roles & allowed or request.user.is_superuser):
            return redirect("training:my_training")

    sessions = tr.sessions.all()
    notes = tr.training_notes.all()
    if not (request.user.is_superuser or request.user.roles.filter(role__in=["MENTOR", "EXAMINER", "STAFF", "ADMIN", "SUPERADMIN"]).exists()):
        notes = notes.filter(is_internal=False)

    return render(request, "training/detail.html", {
        "training_request": tr,
        "sessions": sessions,
        "notes": notes,
    })


@mentor_required
def mentor_dashboard(request):
    """View for mentors to see their assigned students."""
    assigned = TrainingRequest.objects.filter(
        assigned_mentor=request.user,
        status__in=[TrainingRequestStatus.ACCEPTED, TrainingRequestStatus.IN_PROGRESS],
    )
    return render(request, "training/mentor_dashboard.html", {"assigned_requests": assigned})


@mentor_required
def log_session(request, pk):
    tr = get_object_or_404(TrainingRequest, pk=pk)

    if request.method == "POST":
        TrainingSession.objects.create(
            training_request=tr,
            student=tr.student,
            mentor=request.user,
            session_date=request.POST.get("session_date"),
            duration_minutes=int(request.POST.get("duration_minutes", 0)),
            session_type=request.POST.get("session_type", "PRACTICAL"),
            notes=request.POST.get("notes", ""),
            student_performance=request.POST.get("performance", ""),
            passed=request.POST.get("passed") if request.POST.get("passed") else None,
        )
        messages.success(request, "Training session logged.")
        return redirect("training:detail", pk=pk)

    return render(request, "training/log_session.html", {"training_request": tr})
