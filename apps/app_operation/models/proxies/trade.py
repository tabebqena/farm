from django.core.exceptions import ValidationError

from apps.app_transaction.transaction_type import TransactionType

from apps.app_operation.models.operation import Operation


class PurchaseOperation(Operation):
    _issuance_transaction_type = TransactionType.PURCHASE_ISSUANCE
    _payment_transaction_type = TransactionType.PURCHASE_PAYMENT

    url_str = "purchase"
    label = "Purchase Issuance"
    _source_role = "url"
    _dest_role = "post"
    can_pay = True
    is_partially_payable = True
    has_category = True
    category_required = False
    has_invoice = True
    _is_one_shot_operation = False
    has_repayment = False
    max_payment_transaction_count = -1

    class Meta:
        proxy = True
        verbose_name = "Purchase"

    @property
    def payment_source_fund(self):
        return self.source.fund  # clean_source ensures this is a project (pays)

    @property
    def payment_target_fund(self):
        return self.destination.fund  # clean_destination ensures this is a vendor (receives)

    @property
    def project(self):
        return self.source

    @property
    def vendor(self):
        return self.destination

    def clean_source(self):
        if not self.source.project:
            raise ValidationError("Purchase source must be a Project entity.")

    @classmethod
    def get_related_entities(cls, url_entity, config):
        from apps.app_entity.models import Stakeholder, StakeholderRole
        relationships = (
            Stakeholder.objects.filter(
                parent=url_entity, role=StakeholderRole.VENDOR, active=True
            )
            .select_related("target")
            .all()
        )
        return [s.target for s in relationships]

    def clean_destination(self):
        if not self.destination.is_vendor:
            raise ValidationError("Purchase destination must be a Vendor entity.")


class SaleOperation(Operation):
    _issuance_transaction_type = TransactionType.SALE_ISSUANCE
    _payment_transaction_type = TransactionType.SALE_COLLECTION

    url_str = "sale"
    label = "Sale Issuance"
    _source_role = "post"
    _dest_role = "url"
    can_pay = True
    is_partially_payable = True
    has_category = True
    category_required = False
    has_invoice = True
    _is_one_shot_operation = False
    has_repayment = False
    max_payment_transaction_count = -1

    class Meta:
        proxy = True
        verbose_name = "Sale"

    @property
    def payment_source_fund(self):
        return self.source.fund  # clean_source ensures this is a client (pays)

    @property
    def payment_target_fund(self):
        return self.destination.fund  # clean_destination ensures this is a project (collects)

    @property
    def project(self):
        return self.destination

    @property
    def client(self):
        return self.source

    def clean_source(self):
        if not self.source.is_client:
            raise ValidationError("Sale source must be a Client entity.")

    @classmethod
    def get_related_entities(cls, url_entity, config):
        from apps.app_entity.models import Stakeholder, StakeholderRole
        relationships = (
            Stakeholder.objects.filter(
                parent=url_entity, role=StakeholderRole.CLIENT, active=True
            )
            .select_related("target")
            .all()
        )
        return [s.target for s in relationships]

    def clean_destination(self):
        if not self.destination.project:
            raise ValidationError("Sale destination must be a Project entity.")


class ExpenseOperation(Operation):
    _issuance_transaction_type = TransactionType.EXPENSE_ISSUANCE
    _payment_transaction_type = TransactionType.EXPENSE_PAYMENT

    url_str = "expense"
    label = "Expense Issuance"
    _source_role = "url"
    _dest_role = "world"
    can_pay = True
    is_partially_payable = True
    has_category = True
    category_required = True
    has_invoice = False
    _is_one_shot_operation = False
    has_repayment = False
    max_payment_transaction_count = -1

    class Meta:
        proxy = True
        verbose_name = "Expense"

    @property
    def payment_source_fund(self):
        return self.source.fund  # clean_source ensures this is a project (pays)

    @property
    def payment_target_fund(self):
        return self.destination.fund  # clean_destination ensures this is world

    @property
    def project(self):
        return self.source

    def clean_source(self):
        if not self.source.project:
            raise ValidationError("Expense source must be a Project entity.")

    def clean_destination(self):
        if not self.destination.is_world:
            raise ValidationError("Expense destination must be the World entity.")
