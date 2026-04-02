from django.contrib import admin

from .models.operation import Operation


# Register your models here.
@admin.register(Operation)
class OpeartionAdmin(admin.ModelAdmin):
    pass
