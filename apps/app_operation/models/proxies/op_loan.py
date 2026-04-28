from typing import List


from apps.app_entity.models import EntityType
from apps.app_operation.models.operation import Operation
from apps.app_transaction.transaction_type import TransactionType


class LoanOperation(Operation):
    _issuance_transaction_type = TransactionType.LOAN_ISSUANCE
    _payment_transaction_type = TransactionType.LOAN_PAYMENT
    _repayment_transaction_type = TransactionType.LOAN_REPAYMENT
    is_repayable = True

    url_str = "loan"
    label = "Debt Issuance"
    _source_role = "url"
    _dest_role = "post"
    can_pay = False
    # Balance check required: the creditor fund is the real payer. Issuance can succeed
    # with insufficient balance; each individual disbursement is guarded at payment time.
    check_balance_on_payment = True
    is_partially_payable = False
    has_category = False
    category_required = False
    _is_one_shot_operation = False
    has_repayment = True
    repayment_label = "Loan Recovery"
    max_payment_transaction_count = -1

    class Meta:
        proxy = True
        verbose_name = "Loan"

    @property
    def payment_source_fund(self):
        return self.source  # creditor disburses

    @property
    def payment_target_fund(self):
        return self.destination  # debtor receives

    @property
    def creditor(self):
        return self.source

    @property
    def debtor(self):
        return self.destination

    @property
    def _reversable_transaction_types(self) -> List[TransactionType]:
        # Loans must have repayments manually cleared before reversal is allowed.
        return [TransactionType.LOAN_ISSUANCE, TransactionType.LOAN_PAYMENT]

    @classmethod
    def get_related_entities(cls, url_entity, config):
        from django.db.models import Q
        from apps.app_entity.models import Entity

        return (
            Entity.objects.filter(
                entity_type__in=[EntityType.PROJECT, EntityType.PERSON]
            )
            .exclude(pk=url_entity.pk)
            .all()
        )

    @property
    def _implicit_reversable_transaction_types(self) -> List[TransactionType]:
        # Only the issuance is implicitly reversed; payments must be cleared manually.
        return [TransactionType.LOAN_ISSUANCE]
