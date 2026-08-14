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
    has_invoice = False
    has_capital_valuation = True

    class Meta:
        proxy = True
        verbose_name = "Capital Loss"

    def clean_destination(self):
        if not self.destination.is_system:
            raise ValidationError("Capital Loss destination must be the System entity.")

    def add_valuation(self, product, amount, officer=None, notes=""):
        """
        Link *product* to a value-only capital loss of *amount* (negative).

        The operation must already be saved. Creates a ``ProductCapitalValuation``
        row — no ``InvoiceItem`` and no ``InventoryMovementLine`` are created
        (the loss is value-only). Guards (ownership, template compatibility,
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
