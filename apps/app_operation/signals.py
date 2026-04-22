import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.app_base.debug import DebugContext, debug_signal

logger = logging.getLogger(__name__)


@debug_signal("create_initial_period")
def create_initial_period(sender, instance, created, **kwargs):
    """Auto-create an opening FinancialPeriod whenever a real (non-virtual) Entity is created."""
    DebugContext.log(f"Evaluating create_initial_period for {sender.__name__}", {
        "instance_pk": instance.pk,
        "created": created,
        "is_world": getattr(instance, "is_world", False),
        "is_system": getattr(instance, "is_system", False),
    })

    if not created:
        DebugContext.log("Skipping: entity already existed")
        return
    if instance.is_world or instance.is_system:
        DebugContext.log("Skipping: system or world entity")
        return

    from apps.app_operation.models.period import FinancialPeriod

    with DebugContext.section(f"Creating initial FinancialPeriod", {
        "entity_pk": instance.pk,
        "entity_name": str(instance),
        "start_date": str(instance.created_at.date()),
    }):
        period = FinancialPeriod.objects.create(
            entity=instance,
            start_date=instance.created_at.date(),
        )
        DebugContext.success("Initial FinancialPeriod created", {"period_pk": period.pk})


def register():
    from apps.app_entity.models import Entity

    # post_save.connect(create_initial_period, sender=Entity)
    DebugContext.log("app_operation.signals registered (initial_period signal disabled)")
