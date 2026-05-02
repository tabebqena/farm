from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.app_base.form_logging import LoggingFormMixin
from apps.app_operation.models.operation_type import OperationType
from .models import AdjustmentType


class AccountingAdjustmentForm(LoggingFormMixin, forms.Form):
    """Form for recording an accounting adjustment on PURCHASE, SALE, or EXPENSE operations."""

    type = forms.ChoiceField(
        label=_("Adjustment Type"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    amount = forms.DecimalField(
        label=_("Amount"),
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=20,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control amount-input",
                "step": "0.01",
                "placeholder": "0.00",
                "inputmode": "decimal",
            }
        ),
    )

    reason = forms.CharField(
        label=_("Reason"),
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    date = forms.DateField(
        label=_("Date"),
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )

    def __init__(self, *args, operation_type=None, **kwargs):
        super().__init__(*args, **kwargs)

        if operation_type == OperationType.PURCHASE:
            # All PURCHASE types excluding item corrections
            choices = [
                ("", "---"),
                (AdjustmentType.PURCHASE_RETURN, AdjustmentType.PURCHASE_RETURN.label),
                (AdjustmentType.PURCHASE_DISCOUNT, AdjustmentType.PURCHASE_DISCOUNT.label),
                (AdjustmentType.PURCHASE_OVERCHARGE, AdjustmentType.PURCHASE_OVERCHARGE.label),
                (AdjustmentType.PURCHASE_SHORTAGE, AdjustmentType.PURCHASE_SHORTAGE.label),
                (AdjustmentType.PURCHASE_DAMAGE, AdjustmentType.PURCHASE_DAMAGE.label),
                (AdjustmentType.PURCHASE_UNDERCHARGE, AdjustmentType.PURCHASE_UNDERCHARGE.label),
                (AdjustmentType.PURCHASE_TAX_ADDITION, AdjustmentType.PURCHASE_TAX_ADDITION.label),
                (AdjustmentType.PURCHASE_FREIGHT, AdjustmentType.PURCHASE_FREIGHT.label),
                (AdjustmentType.PURCHASE_GENERAL_REDUCTION, AdjustmentType.PURCHASE_GENERAL_REDUCTION.label),
                (AdjustmentType.PURCHASE_GENERAL_INCREASE, AdjustmentType.PURCHASE_GENERAL_INCREASE.label),
            ]
        elif operation_type == OperationType.SALE:
            # All SALE types excluding item corrections
            choices = [
                ("", "---"),
                (AdjustmentType.SALE_RETURN, AdjustmentType.SALE_RETURN.label),
                (AdjustmentType.SALE_DISCOUNT, AdjustmentType.SALE_DISCOUNT.label),
                (AdjustmentType.SALE_OVERCHARGE, AdjustmentType.SALE_OVERCHARGE.label),
                (AdjustmentType.SALE_SHORTAGE, AdjustmentType.SALE_SHORTAGE.label),
                (AdjustmentType.SALE_DAMAGE, AdjustmentType.SALE_DAMAGE.label),
                (AdjustmentType.SALE_WRITE_OFF, AdjustmentType.SALE_WRITE_OFF.label),
                (AdjustmentType.SALE_UNDERCHARGE, AdjustmentType.SALE_UNDERCHARGE.label),
                (AdjustmentType.SALE_TAX_ADDITION, AdjustmentType.SALE_TAX_ADDITION.label),
                (AdjustmentType.SALE_LATE_FEE, AdjustmentType.SALE_LATE_FEE.label),
                (AdjustmentType.SALE_GENERAL_REDUCTION, AdjustmentType.SALE_GENERAL_REDUCTION.label),
                (AdjustmentType.SALE_GENERAL_INCREASE, AdjustmentType.SALE_GENERAL_INCREASE.label),
            ]
        elif operation_type == OperationType.EXPENSE:
            # Only EXPENSE general types
            choices = [
                ("", "---"),
                (AdjustmentType.EXPENSE_GENERAL_INCREASE, AdjustmentType.EXPENSE_GENERAL_INCREASE.label),
                (AdjustmentType.EXPENSE_GENERAL_REDUCTION, AdjustmentType.EXPENSE_GENERAL_REDUCTION.label),
            ]
        else:
            choices = [("", "---")]

        self.fields["type"].choices = choices

    def clean(self):
        cleaned_data = super().clean()
        adj_type = cleaned_data.get("type")
        reason = cleaned_data.get("reason")

        # Require reason for general adjustment types
        if adj_type and AdjustmentType.is_general(adj_type) and not reason:
            raise forms.ValidationError(
                _("Reason is required for general adjustment types.")
            )

        return cleaned_data
