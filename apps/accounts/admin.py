from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Platform access", {"fields": ("is_platform_admin",)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Platform access", {"fields": ("is_platform_admin",)}),
    )
