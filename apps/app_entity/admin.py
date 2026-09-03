"""Admin configuration for the entity app.

Registers the :class:`Entity` and :class:`Stakeholder` models.
"""

from django.contrib import admin

from .models import Entity, Stakeholder


@admin.register(Entity)
class EntityClass(admin.ModelAdmin):
    """Admin for :class:`Entity`."""

    ...



@admin.register(Stakeholder)
class StakeholderClass(admin.ModelAdmin):
    """Admin for :class:`Stakeholder`."""

    ...
