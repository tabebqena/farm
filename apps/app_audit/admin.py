"""Read-only admin registrations for the audit trail.

Audit records are written by the app and the ``purge_savelogs`` command only;
the admin is a read/inspection surface, so add/change/delete are all disabled.
"""

from django.contrib import admin

from .models import ActionTrace, SaveLog


@admin.register(ActionTrace)
class ActionTraceAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "actor",
        "method",
        "action",
        "path",
        "status",
        "duration_ms",
    )
    list_filter = ("status", "method", "created_at")
    search_fields = ("path", "action", "actor__username", "error")
    date_hierarchy = "created_at"
    readonly_fields = (
        "created_at",
        "actor",
        "method",
        "path",
        "action",
        "payload",
        "status",
        "error",
        "root_app",
        "root_model",
        "root_pk",
        "group_key",
        "duration_ms",
        "ip",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SaveLog)
class SaveLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "app_label",
        "model",
        "object_id",
        "kind",
        "is_derived",
        "role",
        "reason_code",
        "trace",
    )
    list_filter = ("is_derived", "kind", "app_label", "model", "created_at")
    search_fields = ("object_id", "object_repr", "role", "reason_code")
    date_hierarchy = "created_at"
    readonly_fields = (
        "trace",
        "created_at",
        "actor",
        "app_label",
        "model",
        "object_id",
        "object_repr",
        "kind",
        "new_shape",
        "is_derived",
        "role",
        "reason_code",
        "reason_text",
        "origin",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
