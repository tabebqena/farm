from django.core.exceptions import ValidationError

from apps.app_entity.models import EntityType
from apps.app_operation.models.operation import Operation
from apps.app_transaction.transaction_type import TransactionType


class InternalTransferOperation(Operation):
    _issuance_transaction_type = TransactionType.INTERNAL_TRANSFER_ISSUANCE
    _payment_transaction_type = TransactionType.INTERNAL_TRANSFER_PAYMENT

    url_str = "internal-transfer"
    label = "Internal Transfer"
    _source_role = "url"
    _dest_role = "post"
    can_pay = False
    is_partially_payable = False
    has_category = False
    category_required = False
    _is_one_shot_operation = True
    has_repayment = False
    max_payment_transaction_count = 1

    class Meta:
        proxy = True
        verbose_name = "Internal Transfer"

    @property
    def payment_source_fund(self):
        return self.source.fund  # clean ensures this is an internal entity

    @property
    def payment_target_fund(self):
        return self.destination.fund  # clean ensures this is an internal entity

    @classmethod
    def get_related_entities(cls, url_entity, config):
        from apps.app_entity.models import Entity

        return (
            Entity.objects.filter(entity_type=EntityType.PERSON)
            .exclude(pk=url_entity.pk)
            .all()
        )

    def clean(self):
        if not self.source.is_internal:
            raise ValidationError(
                "Internal Transfer source must be an internal entity."
            )
        if not self.destination.is_internal:
            raise ValidationError(
                "Internal Transfer destination must be an internal entity."
            )
        if self.source.is_system or self.source.is_world:
            raise ValidationError(
                "Internal Transfer source cannot be a system or world entity."
            )
        if self.destination.is_system or self.destination.is_world:
            raise ValidationError(
                "Internal Transfer destination cannot be a system or world entity."
            )
        source_fund = self.source.fund
        if source_fund.balance < self.amount:
            raise ValidationError(
                f"Insufficient funds: source fund balance ({source_fund.balance}) "
                f"is less than transfer amount ({self.amount})."
            )
        return super().clean()
