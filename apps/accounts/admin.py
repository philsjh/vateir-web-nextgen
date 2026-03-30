from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Role, SiteConfig


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("cid", "vatsim_name", "email", "rating", "is_active")
    search_fields = ("cid", "vatsim_name", "email")
    ordering = ("cid",)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "granted_by", "created_at")
    list_filter = ("role",)


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    pass
