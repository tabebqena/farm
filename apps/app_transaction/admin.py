"""Admin configuration for the transaction app (registers :class:`Transaction`)."""

from django.contrib import admin

from .models import Transaction


# Register your models here.
@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    pass
