from decimal import Decimal
import traceback

from django.contrib import messages
from django.db import transaction as db_transaction
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.app_entity.models import Entity, Stakeholder, StakeholderRole
from apps.app_personal_operation.models import Operation, OperationType
from apps.app_personal_operation.views.common import OPERATION_MAP, op_type_dict
from apps.app_transaction.models import Transaction, TransactionType


def get_theming(canonical_op_type):
    inflow_types = [
        "CASH_INJECTION",
        "PROJECT_REFUND",
        "PROFIT_DISTRIBUTION",
        "DEBT_REPAYMENT",
    ]
    category = "inflow" if canonical_op_type in inflow_types else "outflow"

    if category == "inflow":
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
        # if config.get("dest_type") == "project":
        #     entities = entities.filter(project__isnull=False)
        # if config.get("dest_type") == "person":
        #     entities = entities.filter(person__isnull=False)
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
    return entities if entities else []


def operation_create_factory(request, op_type, pk):
    canonical_op_type: OperationType = op_type_dict.get(op_type)
    if not canonical_op_type:
        return HttpResponseBadRequest(f"Unsupported operation {op_type}")

    config = OPERATION_MAP.get(canonical_op_type, {})
    if not config:
        return HttpResponseBadRequest(
            f"Operation {canonical_op_type} has no configuration."
        )
    config_source = config["source"]
    config_dest = config["dest"]
    # 1. Resolve Entities
    world_entity = None
    if config_source == "world" or config_dest == "world":
        world_entity = Entity.objects.filter(is_world=True).first()
    url_entity = get_object_or_404(Entity, pk=pk)
    officer = get_object_or_404(Entity, user=request.user)

    if request.method == "POST":
        secondary_pk = request.POST.get("secondary_entity")
        secondary_entity = (
            get_object_or_404(Entity, pk=secondary_pk) if secondary_pk else None
        )

        # 2. Assign Source and Destination based on Map
        source, destination = None, None

        if config["source"] == "world":
            source = world_entity
        elif config["source"] == "url":
            source = url_entity
        elif config["source"] == "post":
            source = secondary_entity

        if config["dest"] == "world":
            destination = world_entity
        elif config["dest"] == "url":
            destination = url_entity
        elif config["dest"] == "post":
            destination = secondary_entity

        # 3. Execution
        try:
            with db_transaction.atomic():
                op = Operation.objects.create(
                    operation_type=canonical_op_type,
                    source=source,
                    destination=destination,
                    amount=request.POST.get("amount"),
                    date=request.POST.get("date") or timezone.now().date(),
                    description=request.POST.get("description", ""),
                    officer=officer,
                )
            messages.success(request, f"{config['label']} recorded successfully.")
            return redirect("operation_detail_view", pk=op.pk)
        except Exception as e:
            traceback.print_exc()
            messages.error(request, f"Transaction Error: {str(e)}")

    entities = get_related_entities(canonical_op_type, url_entity, config)
    theme_color, theme_icon = get_theming(canonical_op_type)

    context = {
        "primary": url_entity,
        "config": config,
        "op_type": canonical_op_type,
        "today": timezone.now().date(),  # Pre-filled date
        "entities": entities,
        "theme_color": theme_color,
        "theme_icon": theme_icon,
    }

    return render(request, "app_personal_operation/generic_form.html", context)


def record_transaction_repayment(request, pk):
    operation = get_object_or_404(Operation, pk=pk, operation_type=OperationType.LOAN)

    # Calculate the current balance based on existing transactions
    # (Assuming repayments are marked or have a specific flow)
    # total_repaid = operation.transactions.filter(is_repayment=True)...
    amount = request.POST.get("amount") or 0
    date = request.POST.get("date") or timezone.now().date()
    note = request.POST.get("note") or ""

    if request.method == "POST":

        try:
            officer = get_object_or_404(Entity, user=request.user)

            with db_transaction.atomic():
                # We create a new Transaction inside the SAME operation
                # This transaction flips the direction of the original loan
                tx = Transaction.create(
                    source=operation.destination.fund,  # Debtor pays
                    target=operation.source.fund,  # Creditor receives
                    document=operation,
                    type=TransactionType.LOAN_REPAYMENT,
                    amount=Decimal(amount),
                    officer=officer,
                    description=f"Repayment of {operation.pk}",
                    note=note,
                    date=date,
                )
            messages.success(
                request, f"Transaction of {amount} added to Operation #{operation.pk}"
            )
            return redirect("operation_detail_view", pk=operation.pk)
        except Exception as e:
            traceback.print_exc()
            messages.error(request, f"Error: {str(e)}")

    return render(
        request,
        "app_personal_operation/add_repayment_form.html",
        {
            "operation": operation,
            "date": date,
            "amount": amount,
            "note": note,
        },
    )
