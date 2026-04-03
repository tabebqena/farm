import traceback

from django.contrib import messages
from django.db import transaction as db_transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.app_entity.models import Entity
from apps.app_operation.models import FinancialCategory, Operation
from apps.app_operation.models.proxies import PROXY_MAP, get_canonical_type


def operation_create_factory(request, op_type, pk):
    proxy_cls = get_canonical_type(op_type)
    if not proxy_cls:
        return HttpResponseBadRequest(f"Unsupported operation {op_type}")
    canonical_op_type = next(t for t, c in PROXY_MAP.items() if c is proxy_cls)
    data = proxy_cls.resolve_request(pk, request)
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
    amount = 0
    date = timezone.now()
    description = ""
    note = ""
    formset = None

    # 3. Handle POST
    if request.method == "POST":
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
                    amount = float(request.POST.get("amount"))
                    date = request.POST.get("date") or date
                    description = request.POST.get("description", "")
                    op = proxy_cls.objects.create(
                        operation_type=canonical_op_type,
                        source=data["source_entity"],
                        destination=data["dest_entity"],
                        amount=amount,
                        date=date,
                        description=description,
                        officer=officer,
                    )
                    # can_pay indicates whether the user can control the payment from the UI or not
                    # Other operations are payable from the backend
                    amount_paid = request.POST.get("amount_paid")
                    amount_paid = float(amount_paid if amount_paid else "0")
                    can_pay = data.get("can_pay")
                    if can_pay:
                        if amount_paid > amount:
                            raise ValueError(
                                f"Error: paid amount {amount_paid} is more than the total {amount}"
                            )

                        if (
                            not data.get("is_partially_payable")
                            and amount_paid < amount
                        ):
                            raise ValueError(
                                f"You can't pay less than {amount} for this operation."
                            )
                        if amount_paid > 0:
                            tx = op.create_payment_transaction(
                                amount_paid,
                                officer,
                                date=request.POST.get("date") or timezone.now().date(),
                                description=f"Instant payment for the operation {op.operation_type} {op.pk}",
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
    entities = proxy_cls.get_related_entities(data["url_entity"], data)
    theme_color, theme_icon = data["theme_color"], data["theme_icon"]

    categories = FinancialCategory.objects.filter(
        parent_entity=data["url_entity"],  # or project
        # category_type=operation_type,
        is_active=True,
    )

    context = {
        "primary": data["url_entity"],
        "config": data,
        "op_type": canonical_op_type,
        "today": timezone.now().date(),
        "entities": entities,
        "theme_color": theme_color,
        "theme_icon": theme_icon,
        "formset": formset,
        "is_partially_payable": data.get("is_partially_payable"),
        "can_pay": data.get("can_pay"),
        "categories": categories,
        # Prefill form
        "amount": amount if amount != 0 else "",
        "date": date,
        "description": description,
    }

    return render(request, "app_operation/generic_form.html", context)
