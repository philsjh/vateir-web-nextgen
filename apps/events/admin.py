from django.contrib import admin
from .models import Event, EventPosition, EventAvailability


class EventPositionInline(admin.TabularInline):
    model = EventPosition
    extra = 1


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "start_datetime", "is_published", "is_featured")
    list_filter = ("is_published", "is_featured")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [EventPositionInline]


admin.site.register(EventAvailability)
