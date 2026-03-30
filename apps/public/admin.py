from django.contrib import admin
from .models import StaffMember, InfoPage


@admin.register(StaffMember)
class StaffMemberAdmin(admin.ModelAdmin):
    list_display = ("name", "position_title", "display_order", "is_active")
    list_filter = ("is_active",)
    ordering = ("display_order",)


@admin.register(InfoPage)
class InfoPageAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "is_published", "display_order")
    prepopulated_fields = {"slug": ("title",)}
