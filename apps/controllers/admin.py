from django.contrib import admin
from .models import Controller, ControllerStats, Position, ATCSession, LiveSession, Endorsement, VisitorRequest


@admin.register(Controller)
class ControllerAdmin(admin.ModelAdmin):
    list_display = ("cid", "first_name", "last_name", "rating", "is_active", "visitor_status")
    list_filter = ("is_active", "visitor_status", "rating")
    search_fields = ("cid", "first_name", "last_name")


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("callsign", "name", "position_type", "airport_icao", "is_home")
    list_filter = ("position_type", "is_home")


admin.site.register(ControllerStats)
admin.site.register(ATCSession)
admin.site.register(LiveSession)


@admin.register(Endorsement)
class EndorsementAdmin(admin.ModelAdmin):
    list_display = ("cid", "type", "position", "instructor_cid", "expires_at", "created_at")
    list_filter = ("type",)
    search_fields = ("cid", "position")


@admin.register(VisitorRequest)
class VisitorRequestAdmin(admin.ModelAdmin):
    list_display = ("cid", "status", "reason", "created_at")
    list_filter = ("status",)
    search_fields = ("cid",)
