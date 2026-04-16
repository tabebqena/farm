from django.contrib import admin

from .models import Entity, Fund, Stakeholder


@admin.register(Entity)
class EntityClass(admin.ModelAdmin): ...


@admin.register(Stakeholder)
class StakeholderClass(admin.ModelAdmin): ...


@admin.register(Fund)
class FundClass(admin.ModelAdmin): ...
