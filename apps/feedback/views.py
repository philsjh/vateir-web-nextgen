from django.contrib import messages
from django.shortcuts import redirect, render

from apps.controllers.models import Controller
from .models import Feedback


def submit_feedback(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        cid = request.POST.get("cid", "").strip()
        content = request.POST.get("content", "").strip()

        errors = []
        if not name:
            errors.append("Name is required.")
        if not cid or not cid.isdigit():
            errors.append("A valid VATSIM CID is required.")
        if not content:
            errors.append("Feedback content is required.")

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, "feedback/submit.html", {
                "form_data": request.POST,
            })

        # Link to controller if selected
        controller_cid = request.POST.get("controller_cid", "").strip()
        controller = None
        if controller_cid and controller_cid.isdigit():
            controller = Controller.objects.filter(pk=int(controller_cid)).first()

        Feedback.objects.create(
            submitter_name=name,
            submitter_email=request.POST.get("email", ""),
            submitter_cid=int(cid),
            controller=controller,
            controller_callsign=request.POST.get("callsign", ""),
            feedback_type=request.POST.get("feedback_type", "COMPLIMENT"),
            content=content,
        )
        messages.success(request, "Thank you for your feedback!")
        return redirect("feedback:thanks")

    return render(request, "feedback/submit.html")


def thanks(request):
    return render(request, "feedback/thanks.html")
