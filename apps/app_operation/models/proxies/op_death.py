"""Death-operation proxy.

:class:`DeathOperation` records the death of an individual animal; as a stock
event it also drives the corresponding inventory movement.
"""

from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation, StockEventMixin


class DeathOperation(StockEventMixin, Operation):
    """
    Records a livestock death event.

    A death removes an existing Animal/Batch from active inventory with no cash
    flow — the project's asset value is written off to the system entity.
    The invoice item links to the existing Animal/Batch (same as CAPITAL_LOSS),
    but signals to the save handler that the asset should be marked as deceased
    rather than merely devalued.
    """

    url_str = "death"
    label = "Death"
    _source_role = "url"
    _dest_role = "system"

    class Meta:
        proxy = True
        verbose_name = "Death"

    def clean_source(self):
        if not self.source.is_project:
            raise ValidationError("Death source must be a Project entity.")

    def clean_destination(self):
        if not self.destination.is_system:
            raise ValidationError("Death destination must be the System entity.")
