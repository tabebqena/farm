from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation


class CapitalLossOperation(Operation):
    url_str = "capital-loss"
    label = "Capital Loss Issuance"
    _source_role = "url"
    _dest_role = "system"
    can_pay = False
    check_balance_on_payment = False
    is_partially_payable = False
    has_category = False
    category_required = False
    has_repayment = False
    has_invoice = True

    class Meta:
        proxy = True
        verbose_name = "Capital Loss"

    def clean_destination(self):
        if not self.destination.is_system:
            raise ValidationError("Capital Loss destination must be the System entity.")
