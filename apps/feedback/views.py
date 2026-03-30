from django.contrib import messages
from django.shortcuts import redirect, render

from .models import Feedback


def submit_feedback(request):
    if request.method == "POST":
        Feedback.objects.create(
            submitter_name=request.POST.get("name", ""),
            submitter_email=request.POST.get("email", ""),
            submitter_cid=request.POST.get("cid") or None,
            controller_callsign=request.POST.get("callsign", ""),
            feedback_type=request.POST.get("feedback_type", "COMPLIMENT"),
            content=request.POST.get("content", ""),
        )
        messages.success(request, "Thank you for your feedback!")
        return redirect("feedback:thanks")
    return render(request, "feedback/submit.html")


def thanks(request):
    return render(request, "feedback/thanks.html")
