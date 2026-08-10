from typing import List

from django.core.exceptions import ValidationError

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

    def clean_source(self):
        if not (self.source.is_person or self.source.is_project):
            raise ValidationError(
                "Loan source (creditor) must be a Person or Project entity."
            )

    def clean_destination(self):
        if not (self.destination.is_person or self.destination.is_project):
            raise ValidationError(
                "Loan destination (debtor) must be a Person or Project entity."
            )

    def clean(self):
        # Enforce that creditor and debtor are distinct entities.
        if (
            self.source_id is not None
            and self.destination_id is not None
            and self.source_id == self.destination_id
        ):
            raise ValidationError(
                "Loan source (creditor) and destination (debtor) must be different entities."
            )
        return super().clean()

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
        # Only the issuance is implicitly reversed; payments & repayments must be cleared manually.
        return [TransactionType.LOAN_ISSUANCE]

    def _requires_transaction_reversal(self, all_txs) -> bool:
        if super()._requires_transaction_reversal(all_txs):
            return True
        repayments = all_txs.filter(
            type=TransactionType.LOAN_REPAYMENT,
            reversal_of__isnull=True,
            reversed_by__isnull=True,
        )
        return repayments.exists()
