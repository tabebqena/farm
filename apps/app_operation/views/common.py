from django.core.exceptions import BadRequest
from django.db.models import Q
from django.shortcuts import get_object_or_404

from apps.app_entity.models import Entity, Stakeholder, StakeholderRole
from apps.app_operation.models.operation_type import OperationType

# can_pay key indicate whether the user can pay the opoeration from the UI
# Almost all operations are payable
# But some (most) of them are left to the backend

# is_partially_payable key indicates whether the user can pay partially or not

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


def parse_config(proxy_cls, url_pk, request) -> dict:
    if not proxy_cls:
        raise BadRequest("Unknown operation type.")

    url_entity = get_object_or_404(Entity, pk=url_pk)
    source_role = proxy_cls._source_role
    dest_role = proxy_cls._dest_role

    world_entity = None
    if source_role == "world" or dest_role == "world":
        world_entity = Entity.objects.filter(is_world=True).first()
    system_entity = None
    if source_role == "system" or dest_role == "system":
        system_entity = Entity.objects.filter(is_system=True).first()

    secondary_pk = request.POST.get("secondary_entity")
    secondary_entity = get_object_or_404(Entity, pk=secondary_pk) if secondary_pk else None

    def resolve(role):
        if role == "world":
            return world_entity
        if role == "system":
            return system_entity
        if role == "url":
            return url_entity
        if role == "post":
            return secondary_entity
        return None

    return {
        # Static config from proxy class
        "proxy_cls": proxy_cls,
        "label": proxy_cls.label,
        "url_str": proxy_cls.url_str,
        "source": source_role,
        "dest": dest_role,
        "can_pay": proxy_cls.can_pay,
        "is_partially_payable": proxy_cls.is_partially_payable,
        "has_category": proxy_cls.has_category,
        "category_required": proxy_cls.category_required,
        "has_repayment": proxy_cls.has_repayment,
        "has_invoice": proxy_cls.has_invoice,
        "repayment_transaction_type": getattr(proxy_cls, "_repayment_transaction_type", None),
        "theme_color": proxy_cls.theme_color,
        "theme_icon": proxy_cls.theme_icon,
        # Runtime-resolved entities
        "url_entity": url_entity,
        "secondary_entity": secondary_entity,
        "source_entity": resolve(source_role),
        "dest_entity": resolve(dest_role),
    }


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

    elif canonical_op_type == OperationType.WORKER_ADVANCE.value:
        shareholder_relationships = (
            Stakeholder.objects.filter(
                parent=url_entity, role=StakeholderRole.WORKER, active=True
            )
            .select_related("target")
            .all()
        )
        entities = [s.target for s in shareholder_relationships]

    return entities if entities else []
