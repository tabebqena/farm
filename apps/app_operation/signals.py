from django.db.models.signals import post_save
from django.dispatch import receiver


def create_initial_period(sender, instance, created, **kwargs):
    """Auto-create an opening FinancialPeriod whenever a real (non-virtual) Entity is created."""
    if not created:
        return
    if instance.is_world or instance.is_system:
        return
    from apps.app_operation.models.period import FinancialPeriod

    FinancialPeriod.objects.create(
        entity=instance,
        start_date=instance.created_at.date(),
    )


def register():
    from apps.app_entity.models import Entity

    post_save.connect(create_initial_period, sender=Entity)
