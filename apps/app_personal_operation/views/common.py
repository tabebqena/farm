from apps.app_personal_operation.models import OperationType

op_type_dict = {
    "cash-injection": OperationType.CASH_INJECTION.value,
    "cash-withdrawal": OperationType.CASH_WITHDRAWAL.value,
    "project-funding": OperationType.PROJECT_FUNDING.value,
    "project-refunding": OperationType.PROJECT_REFUND.value,
    "profit-distribution": OperationType.PROFIT_DISTRIBUTION.value,
    "loss-coverage": OperationType.LOSS_COVERAGE.value,
    "internal-transfer": OperationType.INTERNAL_TRANSFER.value,
    "loan": OperationType.LOAN,
    # "loan-repayment": OperationType.LOAN_REPAYMENT,
}

OPERATION_MAP = {
    # the source is alway the world & the dest is the the person pk in the url.
    OperationType.CASH_INJECTION.value: {
        "source": "world",
        "dest": "url",
        "label": "Cash Injection",
    },
    # the source is the the person pk in the url,  the dest is alway the world.
    OperationType.CASH_WITHDRAWAL.value: {
        "source": "url",
        "dest": "world",
        "label": "Cash Withdrawal",
    },
    # the destination is the project selected in the form
    # The source is the person pk in the url
    OperationType.PROJECT_FUNDING.value: {
        "source": "url",
        "dest": "post",
        "label": "Project Funding",
        # "dest_type": "project",
    },
    # The source is the person pk in the url
    # the destination is the project selected in the form
    OperationType.PROJECT_REFUND.value: {
        "source": "post",
        "dest": "url",
        "label": "Project Refund",
    },
    # The source is the project pk in the url
    # dest is the post
    OperationType.PROFIT_DISTRIBUTION.value: {
        "source": "url",
        "dest": "post",
        "label": "Profit Distribution",
    },
    # The source is the person pk in the url
    # the destination is the project selected in the form
    OperationType.LOSS_COVERAGE.value: {
        "source": "url",
        "dest": "post",
        "label": "Loss Coverage",
    },
    OperationType.INTERNAL_TRANSFER.value: {
        "source": "url",
        "dest": "post",
        "label": "Internal Transfer",
        "source_internal": True,
        "dest_internal": True,
    },
    # The source is the person pk in the url
    # the destination is the other party selected in the form
    OperationType.LOAN.value: {
        "source": "url",
        "dest": "post",
        "label": "Debt Issuance",
    },
    # OperationType.LOAN_PAYMENT.value: {
    #     "source": "url",
    #     "dest": "post",
    #     "label": "Loan Payment",
    # },
    # OperationType.LOAN_REPAYMENT.value: {
    #     "source": "url",
    #     "dest": "post",
    #     "label": "Loan Repayment",
    # },
}
