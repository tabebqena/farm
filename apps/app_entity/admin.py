from django.contrib import admin
from .models import Entity, Stakeholder, Person, Project, Fund


@admin.register(Entity)
class EntityClass(admin.ModelAdmin): ...


@admin.register(Stakeholder)
class StakeholderClass(admin.ModelAdmin): ...


@admin.register(Person)
class PersonClass(admin.ModelAdmin): ...


@admin.register(Project)
class ProjectClass(admin.ModelAdmin): ...


@admin.register(Fund)
class FundClass(admin.ModelAdmin): ...
