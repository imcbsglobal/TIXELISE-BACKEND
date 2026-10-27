from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    list_display = ("created_at", "tenant", "actor_label", "action", "target_type", "target_id")
    list_filter = ("action", "target_type", "tenant")
    search_fields = ("actor_label", "action", "target_type", "target_id", "correlation_id")
    readonly_fields = tuple(field.name for field in AuditLog._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
