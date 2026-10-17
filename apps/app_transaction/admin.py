"""Admin configuration for the transaction app (registers :class:`Transaction`)."""

from django.contrib import admin

from apps.app_base.admin_guard import SoftDeleteAdminGuardMixin

from .models import Transaction


# Register your models here.
@admin.register(Transaction)
class TransactionAdmin(SoftDeleteAdminGuardMixin, admin.ModelAdmin):
    """Admin for :class:`Transaction`."""

    pass
