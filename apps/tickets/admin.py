from django.contrib import admin
from .models import Ticket, TicketReply, TicketStatusChange


class TicketReplyInline(admin.TabularInline):
    model = TicketReply
    extra = 0


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("reference", "subject", "status", "priority", "created_by", "assigned_to", "created_at")
    list_filter = ("status", "priority", "category", "sla_breached")
    search_fields = ("reference", "subject", "created_by__vatsim_name")
    inlines = [TicketReplyInline]


@admin.register(TicketStatusChange)
class TicketStatusChangeAdmin(admin.ModelAdmin):
    list_display = ("ticket", "old_status", "new_status", "changed_by", "created_at")
