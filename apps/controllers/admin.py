from django.contrib import admin
from .models import Controller, ControllerStats, Position, ATCSession, LiveSession


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
