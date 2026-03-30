from django.contrib import admin
from .models import TrainingRequest, TrainingSession, TrainingNote


@admin.register(TrainingRequest)
class TrainingRequestAdmin(admin.ModelAdmin):
    list_display = ("student", "requested_rating", "status", "assigned_mentor", "created_at")
    list_filter = ("status",)


@admin.register(TrainingSession)
class TrainingSessionAdmin(admin.ModelAdmin):
    list_display = ("student", "mentor", "session_type", "session_date", "passed")
    list_filter = ("session_type",)


admin.site.register(TrainingNote)
