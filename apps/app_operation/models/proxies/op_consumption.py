from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation, StockEventMixin


class ConsumptionOperation(StockEventMixin, Operation):
    """
    Records internal consumption of a product we own.

    Consumption removes an existing inventory asset from the project with no
    cash flow — the project's asset value is written off to the system entity.
    The invoice item links to the existing product/asset being consumed.
    """

    url_str = "consumption"
    label = "Consumption"
    _source_role = "url"
    _dest_role = "system"

    class Meta:
        proxy = True
        verbose_name = "Consumption"

    @property
    def project(self):
        return self.source

    def clean_source(self):
        if not self.source.is_project:
            raise ValidationError("Consumption source must be a Project entity.")

    def clean_destination(self):
        if not self.destination.is_system:
            raise ValidationError("Consumption destination must be the System entity.")
