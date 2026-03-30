from django.contrib import admin
from .models import Feedback


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("feedback_type", "submitter_name", "controller_callsign", "status", "created_at")
    list_filter = ("feedback_type", "status")
    search_fields = ("submitter_name", "controller_callsign", "content")
