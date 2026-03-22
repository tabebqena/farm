import traceback

from django.contrib import messages
from django.core.exceptions import BadRequest
from django.db import transaction as db_transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.app_entity.models import Entity
from apps.app_operation.models import Operation
from apps.app_operation.views.common import (
    get_related_entities,
    get_theming,
    op_type_dict,
    parse_config,
)


def operation_create_factory(request, op_type, pk):
    canonical_op_type = op_type_dict.get(op_type)
    if not canonical_op_type:
        return HttpResponseBadRequest(f"Unsupported operation {op_type}")
    try:
        data = parse_config(canonical_op_type, pk, request)
    except BadRequest as e:
        return HttpResponseBadRequest(e)
    # 1. Resolve Entities
    officer = get_object_or_404(Entity, user=request.user)
    # 2. Setup Formset
    # 'extra=1' provides one empty row by default
    # InvoiceItemFormSet = inlineformset_factory(
    #     Operation,
    #     InvoiceItem,
    #     fields=("product_name", "quantity", "unit_price"),
    #     extra=1,
    #     can_delete=True,
    # )

    # 3. Handle POST
    if request.method == "POST":
        # secondary_entity = data["secondary_entity"]

        # Bind Formset to POST data
        formset = None
        # if canonical_op_type == OperationType.PURCHASE:
        #     formset = InvoiceItemFormSet(request.POST)

        # Determine Source/Destination

        # VALIDATION: Check formset BEFORE accessing cleaned_data
        is_formset_valid = True
        if formset and not formset.is_valid():
            is_formset_valid = False
            messages.error(request, "Please check the items table for errors.")

        if is_formset_valid:
            try:
                with db_transaction.atomic():
                    op = Operation.objects.create(
                        operation_type=canonical_op_type,
                        source=data["source_entity"],
                        destination=data["dest_entity"],
                        amount=request.POST.get("amount"),
                        date=request.POST.get("date") or timezone.now().date(),
                        description=request.POST.get("description", ""),
                        officer=officer,
                    )

                    # Save items if they exist
                    # if formset:
                    #     instances = formset.save(commit=False)
                    #     for instance in instances:
                    #         instance.operation = op  # Link to parent
                    #         instance.save()
                    #     formset.save_m2m()

                messages.success(request, f"{data['label']} recorded successfully.")
                return redirect("operation_detail_view", pk=op.pk)
            except Exception as e:
                traceback.print_exc()
                messages.error(request, f"Transaction Error: {str(e)}")
    else:
        # GET Request: Initialize empty formset
        formset = None
        # if canonical_op_type == OperationType.PURCHASE:
        #     formset = InvoiceItemFormSet()

    # 4. Preparation for Render
    entities = get_related_entities(canonical_op_type, data["url_entity"], data)
    theme_color, theme_icon = get_theming(canonical_op_type)

    print(data)

    context = {
        "primary": data["url_entity"],
        "config": data,
        "op_type": canonical_op_type,
        "today": timezone.now().date(),
        "entities": entities,
        "theme_color": theme_color,
        "theme_icon": theme_icon,
        "formset": formset,
        "isPartiallyPayable": data.get("is_partially_payable"),
        "can_pay": data.get("can_pay"),
    }

    return render(request, "app_operation/generic_form.html", context)
