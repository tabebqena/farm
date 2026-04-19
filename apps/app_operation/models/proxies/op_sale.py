from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation
from apps.app_transaction.transaction_type import TransactionType


class SaleOperation(Operation):
    _issuance_transaction_type = TransactionType.SALE_ISSUANCE
    _payment_transaction_type = TransactionType.SALE_COLLECTION

    url_str = "sale"
    label = "Sale Issuance"
    _source_role = "post"
    _dest_role = "url"
    can_pay = True
    # Balance check required: the client fund is the real payer. Issuance can succeed
    # with insufficient balance; each individual payment is guarded at settlement time.
    check_balance_on_payment = True
    is_partially_payable = True
    has_category = False
    category_required = False
    has_invoice = True
    _is_one_shot_operation = False
    has_repayment = False
    max_payment_transaction_count = -1

    category_type = "SALE"

    class Meta:
        proxy = True
        verbose_name = "Sale"

    @property
    def payment_source_fund(self):
        return self.source  # clean_source ensures this is a client (pays)

    @property
    def payment_target_fund(self):
        return (
            self.destination
        )  # clean_destination ensures this is a project (collects)

    @property
    def project(self):
        return self.destination

    @property
    def client(self):
        return self.source

    def clean_source(self):
        if not self.source.is_client:
            raise ValidationError("Sale source must be a Client entity.")
        from apps.app_entity.models import Stakeholder, StakeholderRole

        if not Stakeholder.objects.filter(
            parent=self.destination,
            target=self.source,
            role=StakeholderRole.CLIENT,
            active=True,
        ).exists():
            raise ValidationError(
                "Sale source must be an active client of the destination project."
            )

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
        if not self.destination.is_project:
            raise ValidationError("Sale destination must be a Project entity.")
