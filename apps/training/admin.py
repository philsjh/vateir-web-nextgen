from django.contrib import admin
from .models import (
    TrainingCourse, TrainingCompetency, TrainingTaskDefinition,
    TrainingRequest, TrainingSession, SessionReport, CompetencyRating,
    StudentTaskProgress, TrainingNote,
)


class TrainingCompetencyInline(admin.TabularInline):
    model = TrainingCompetency
    extra = 1


class TrainingTaskDefinitionInline(admin.TabularInline):
    model = TrainingTaskDefinition
    extra = 1


@admin.register(TrainingCourse)
class TrainingCourseAdmin(admin.ModelAdmin):
    list_display = ("name", "from_rating", "to_rating", "is_active", "display_order")
    inlines = [TrainingCompetencyInline, TrainingTaskDefinitionInline]


@admin.register(TrainingRequest)
class TrainingRequestAdmin(admin.ModelAdmin):
    list_display = ("student", "course", "status", "position", "created_at")
    list_filter = ("status", "course")


@admin.register(TrainingSession)
class TrainingSessionAdmin(admin.ModelAdmin):
    list_display = ("student", "mentor", "session_type", "status", "session_date")
    list_filter = ("session_type", "status")


class CompetencyRatingInline(admin.TabularInline):
    model = CompetencyRating
    extra = 0


@admin.register(SessionReport)
class SessionReportAdmin(admin.ModelAdmin):
    list_display = ("session", "is_published", "created_at")
    inlines = [CompetencyRatingInline]


admin.site.register(TrainingCompetency)
admin.site.register(TrainingTaskDefinition)
admin.site.register(StudentTaskProgress)
admin.site.register(TrainingNote)
