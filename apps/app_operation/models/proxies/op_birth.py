"""Birth-operation proxy.

:class:`BirthOperation` records the birth of animals into the herd; as a stock
event it also drives the corresponding inventory movements.
"""

from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation, StockEventMixin


class BirthOperation(StockEventMixin, Operation):
    """
    Records a livestock birth event.

    A birth creates a new Animal/Batch in inventory with no cash flow —
    the system entity issues the asset value on behalf of the project.
    The invoice item's on-save handler creates the new Animal/Batch object
    (same as PURCHASE), distinguishing this from CAPITAL_GAIN which always
    links to an existing asset.
    """

    url_str = "birth"
    label = "Birth"
    _source_role = "system"
    _dest_role = "url"
    creates_assets = True

    class Meta:
        proxy = True
        verbose_name = "Birth"

    def clean_source(self):
        if not self.source.is_system:
            raise ValidationError("Birth source must be the System entity.")

    def clean_destination(self):
        if not self.destination.is_project:
            raise ValidationError("Birth destination must be a Project entity.")
