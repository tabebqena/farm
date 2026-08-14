from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation


class CapitalGainOperation(Operation):
    url_str = "capital-gain"
    label = "Capital Gain Issuance"
    _source_role = "system"
    _dest_role = "url"
    can_pay = False
    check_balance_on_payment = False
    is_partially_payable = False
    has_category = False
    category_required = False
    has_repayment = False
    has_invoice = False
    has_capital_valuation = True

    class Meta:
        proxy = True
        verbose_name = "Capital Gain"

    def clean_source(self):
        if not self.source.is_system:
            raise ValidationError("Capital Gain source must be the System entity.")

    def clean_destination(self):
        if not self.destination.is_project:
            raise ValidationError(
                "Capital Gain destination must be a Project entity."
            )

    def add_valuation(self, product, amount, officer=None, notes=""):
        """
        Link *product* to a value-only capital gain of *amount* (positive).

        The operation must already be saved. Creates a ``ProductCapitalValuation``
        row — no ``InvoiceItem`` and no ``InventoryMovementLine`` are created
        (the gain is value-only). Guards (ownership, template compatibility,
        product active, signed direction) are enforced by the row's ``clean()``.
        """
        from decimal import Decimal

        from apps.app_inventory.models import ProductCapitalValuation

        entry = ProductCapitalValuation(
            operation=self,
            product=product,
            amount=Decimal(amount),
            date=self.date,
            notes=notes,
            officer=officer,
        )
        entry.full_clean()
        entry.save()
        return entry
