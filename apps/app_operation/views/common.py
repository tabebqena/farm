from django.core.exceptions import BadRequest
from django.db.models import Q
from django.shortcuts import get_object_or_404

from apps.app_entity.models import Entity, Stakeholder, StakeholderRole
from apps.app_operation.models import OperationType

# can_pay key indicate whether the user can pay the opoeration from the UI
# Almost all operations are payable
# But some (most) of them are left to the backend

# is_partially_payable key indicates whether the user can pay partially or not

OPERATION_MAP = {
    # the source is alway the world & the dest is the the person pk in the url.
    OperationType.CASH_INJECTION.value: {
        "source": "world",
        "dest": "url",
        "label": "Cash Injection",
        # "Once Issued, Must be Fully Paid" -> Leave payment for the backend
        #
        "can_pay": False,
        "is_partially_payable": False,
    },
    # the source is the the person pk in the url,  the dest is alway the world.
    OperationType.CASH_WITHDRAWAL.value: {
        "source": "url",
        "dest": "world",
        "label": "Cash Withdrawal",
        # "Once Issued, Must be Fully Paid" -> Leave payment for the backend
        "can_pay": False,
        "is_partially_payable": False,
    },
    # the destination is the project selected in the form
    # The source is the person pk in the url
    OperationType.PROJECT_FUNDING.value: {
        "source": "url",
        "dest": "post",
        "label": "Project Funding",
        # "dest_type": "project",
        # "Once Issued, Must be Fully Paid" -> Leave payment for the backend
        "can_pay": False,
        "is_partially_payable": False,
    },
    # The source is the person pk in the url
    # the destination is the project selected in the form
    OperationType.PROJECT_REFUND.value: {
        "source": "post",
        "dest": "url",
        "label": "Project Refund",
        # "Once Issued, Must be Fully Paid" -> Leave payment for the backend
        "can_pay": False,
        "is_partially_payable": False,
    },
    # The source is the project pk in the url
    # dest is the post
    OperationType.PROFIT_DISTRIBUTION.value: {
        "source": "url",
        "dest": "post",
        "label": "Profit Distribution",
        # "Once Issued, Must be Fully Paid"  -> Leave payment for the backend
        "can_pay": False,
        "is_partially_payable": False,
    },
    # The source is the person pk in the url
    # the destination is the project selected in the form
    OperationType.LOSS_COVERAGE.value: {
        "source": "url",
        "dest": "post",
        "label": "Loss Coverage",
        # "Once Issued, Must be Fully Paid"  -> Leave payment for the backend
        "can_pay": False,
        "is_partially_payable": False,
    },
    OperationType.INTERNAL_TRANSFER.value: {
        "source": "url",
        "dest": "post",
        "label": "Internal Transfer",
        "source_internal": True,
        "dest_internal": True,
        # "Once Issued, Must be Fully Paid"  -> Leave payment for the backend
        "can_pay": False,
        "is_partially_payable": False,
    },
    # The source is the person pk in the url
    # the destination is the other party selected in the form
    OperationType.LOAN.value: {
        "source": "url",
        "dest": "post",
        "label": "Debt Issuance",
        # "Once Issued, Must be Fully Paid"  -> Leave payment for the backend
        "can_pay": False,
        "is_partially_payable": False,
    },
    #
    OperationType.PURCHASE.value: {
        "source": "url",
        "dest": "post",
        "label": "Purchase Issuance",
        "operation_type": OperationType.PURCHASE.value,
        # "Once Issued, can be partially payed"
        "can_pay": True,
        "is_partially_payable": True,
        # Whether it has a Financial category or not.
        "has_category": True,
        "category_required": False,
        # indicates whether this operation should show invoice items table
        "has_invoice": True,
    },
    OperationType.EXPENSE.value: {
        "source": "url",
        "dest": "world",
        "label": "Expense Issuance",
        "operation_type": OperationType.EXPENSE.value,
        # "Once Issued, can be partially paid"
        "can_pay": True,
        "is_partially_payable": True,
        "has_category": True,
        "category_required": True,
        "has_invoice": False,
    },
    OperationType.CAPITAL_GAIN.value: {
        "source": "system",
        "dest": "url",
        "label": "CAPITAL GAIN Issuance",
        "operation_type": OperationType.CAPITAL_GAIN.value,
        # "Once Issued, Once completely paid, by the system, the user has no UI option"
        "can_pay": False,
        "is_partially_payable": False,
        #
        "has_category": False,
        "category_required": False,
        "has_invoice": True,
    },
    OperationType.CAPITAL_LOSS.value: {
        "source": "url",
        "dest": "system",
        "label": "CAPITAL LOSS Issuance",
        "operation_type": OperationType.CAPITAL_LOSS.value,
        # "Once Issued, Once completely paid, by the system, the user has no UI option"
        "can_pay": False,
        "is_partially_payable": False,
        #
        "has_category": False,
        "category_required": False,
        "has_invoice": True,
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

"""
1. Scenario: "Once Issued, No Option to Pay"
Behavior: The transaction is a pure record (like a Quote or an Account-only Invoice). 
No money changes hands at this stage.

Mapping: * canPay: False

isPartiallyPayable: False (or irrelevant)

Result: The "Amount Paid" input is hidden or forced to $ 0.00. 
The entire "Total" is recorded as a pending balance/debt.

2. Scenario: "Once Issued, Must be Fully Paid"
Behavior: The transaction and the payment are one and the same (like a Cash Sale). 
You cannot record the transaction without paying it all.

Mapping: * canPay: True

isPartiallyPayable: False

Result: The "Amount Paid" field automatically mirrors the "Total Amount." 
If the items total $150.00, the Paid field is locked at $150.00.

3. Scenario: "Once Issued, Can be Partially Paid"
Behavior: The user has the option to pay some, all, or none of the amount right now 
(like a Credit Purchase with a Down Payment).

Mapping: * canPay: True

isPartiallyPayable: True

Result: The UI shows the toggle. If the user turns it on, 
they can type "$50.00" into the "Paid" field, 
and the script calculates the remaining "$100.00" balance.
"""


def parse_config(canonical_op_type, url_pk, request) -> dict:
    config = OPERATION_MAP.get(canonical_op_type, {})
    if not config:
        raise BadRequest(f"Operation {canonical_op_type} has no configuration.")
    config["url_entity"] = get_object_or_404(Entity, pk=url_pk)

    world_entity = None
    if config["source"] == "world" or config["dest"] == "world":
        world_entity = Entity.objects.filter(is_world=True).first()
    system_entity = None
    if config["source"] == "system" or config["dest"] == "system":
        system_entity = Entity.objects.filter(is_system=True).first()

    secondary_pk = request.POST.get("secondary_entity")
    if secondary_pk:
        config["secondary_entity"] = (
            get_object_or_404(Entity, pk=secondary_pk) if secondary_pk else None
        )
    if config["source"] == "world":
        config["source_entity"] = world_entity
    if config["source"] == "system":
        config["source_entity"] = system_entity
    elif config["source"] == "url":
        config["source_entity"] = config["url_entity"]
    elif config["source"] == "post":
        config["source_entity"] = config["secondary_entity"]

    if config["dest"] == "world":
        config["dest_entity"] = world_entity
    elif config["dest"] == "system":
        config["dest"] = system_entity
    elif config["dest"] == "url":
        config["dest_entity"] = config["url_entity"]
    elif config["dest"] == "post":
        config["dest_entity"] = config["secondary_entity"]

    return config


def get_theming(canonical_op_type):
    # This if the visualizer own the source fund
    inflow_types = [
        "CASH_INJECTION",
        "PROJECT_REFUND",
        "PROFIT_DISTRIBUTION",
        "DEBT_REPAYMENT",
    ]
    inflow = "inflow" if canonical_op_type in inflow_types else "outflow"

    if inflow == "inflow":
        theme_color = "success"
        theme_icon = "bi-box-arrow-in-down"
    else:
        theme_color = "danger"
        theme_icon = "bi-box-arrow-up-right"
    return theme_color, theme_icon


def get_related_entities(canonical_op_type, url_entity, config):
    entities = None
    config_source = config["source"]
    config_dest = config["dest"]

    if config_dest in ["world", "url"]:
        entities = []
    elif config_dest == "post":
        entities = Entity.objects

    if canonical_op_type in [
        OperationType.PROJECT_FUNDING.value,
        OperationType.PROJECT_REFUND.value,
        OperationType.LOSS_COVERAGE.value,
    ]:
        # 1. We are looking for Projects (Stakeholder parents)
        # 2. Where the Person (url_entity) is a target
        # 3. AND their role is specifically 'shareholder'
        entities = (
            Entity.objects.filter(
                project__isnull=False,
                stakeholders__target=url_entity,
                stakeholders__active=True,
                stakeholders__role=StakeholderRole.SHAREHOLDER,
            )
            .distinct()
            .all()
        )
    elif canonical_op_type == OperationType.INTERNAL_TRANSFER.value:
        entities = (
            Entity.objects.filter(person__isnull=False).exclude(pk=url_entity.pk).all()
        )
    elif canonical_op_type == OperationType.PROFIT_DISTRIBUTION.value:
        shareholder_relationships = (
            Stakeholder.objects.filter(
                parent=url_entity, role=StakeholderRole.SHAREHOLDER, active=True
            )
            .select_related("target")
            .all()
        )
        entities = [s.target for s in shareholder_relationships]
    elif canonical_op_type == OperationType.LOAN.value:
        entities = (
            Entity.objects.filter(
                Q(person__isnull=False) | Q(project__isnull=False),
            )
            .exclude(pk=url_entity.pk)
            .all()
        )
    elif canonical_op_type == OperationType.PURCHASE.value:
        shareholder_relationships = (
            Stakeholder.objects.filter(
                parent=url_entity, role=StakeholderRole.VENDOR, active=True
            )
            .select_related("target")
            .all()
        )
        entities = [s.target for s in shareholder_relationships]

    elif canonical_op_type == OperationType.SALE.value:
        shareholder_relationships = (
            Stakeholder.objects.filter(
                parent=url_entity, role=StakeholderRole.CLIENT, active=True
            )
            .select_related("target")
            .all()
        )
        entities = [s.target for s in shareholder_relationships]
    return entities if entities else []
