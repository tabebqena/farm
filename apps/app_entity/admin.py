from django.contrib import admin

from .models import Entity, Stakeholder


@admin.register(Entity)
class EntityClass(admin.ModelAdmin): ...


@admin.register(Stakeholder)
class StakeholderClass(admin.ModelAdmin): ...
