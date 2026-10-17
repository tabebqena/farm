"""Admin configuration for the entity app.

Registers the :class:`Entity` and :class:`Stakeholder` models.
"""

from django.contrib import admin

from apps.app_base.admin_guard import SoftDeleteAdminGuardMixin

from .models import Entity, Stakeholder


@admin.register(Entity)
class EntityClass(SoftDeleteAdminGuardMixin, admin.ModelAdmin):
    """Admin for :class:`Entity`."""

    ...



@admin.register(Stakeholder)
class StakeholderClass(SoftDeleteAdminGuardMixin, admin.ModelAdmin):
    """Admin for :class:`Stakeholder`."""

    ...
