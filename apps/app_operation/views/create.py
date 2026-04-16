import traceback
from decimal import Decimal

from django.contrib import messages
from django.db import transaction as db_transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _

from apps.app_entity.models import Entity
from apps.app_inventory.forms import InvoiceItemCreateFormSet, InvoiceItemSelectFormSet
from apps.app_inventory.models import Invoice, Product
from apps.app_operation.models import FinancialCategory
from apps.app_operation.models.proxies import PROXY_MAP, get_canonical_type


def _build_formset(proxy_cls, data=None, instance=None, project=None):
    """Return the correct formset class for this operation, bound or unbound."""
    if proxy_cls.creates_assets:
        if data is not None:
            return InvoiceItemCreateFormSet(data, instance=instance, project=project)
        return InvoiceItemCreateFormSet(instance=instance, project=project)
    else:
        if data is not None:
            return InvoiceItemSelectFormSet(data, instance=instance)
        return InvoiceItemSelectFormSet(instance=instance)


def _save_inventory(proxy_cls, bound_formset):
    """
    Called inside an atomic block after the formset is saved.
    - create-mode (PURCHASE/BIRTH): create a Product from each item, link via M2M.
    - select-mode (SALE/DEATH/CAPITAL_GAIN/CAPITAL_LOSS): link the chosen Product via M2M.
    """
    if proxy_cls.creates_assets:
        for form in bound_formset.forms:
            item = form.instance
            if not item.pk:
                continue  # deleted form
            template = item.product  # FK to ProductTemplate
            uid = form.cleaned_data.get("unique_id", "").strip() or None
            product = Product.objects.create(
                product_template=template,
                quantity=item.quantity,
                unit_price=item.unit_price,
                unique_id=uid,
            )
            product.invoice_items.add(item)
    else:
        for form in bound_formset.forms:
            item = form.instance
            if not item.pk:
                continue
            selected = form.cleaned_data.get("selected_product")
            if selected:
                selected.invoice_items.add(item)


def operation_create_factory(request, op_type, pk):
    proxy_cls = get_canonical_type(op_type)
    if not proxy_cls:
        return HttpResponseBadRequest(
            _("Unsupported operation %(op_type)s") % {"op_type": op_type}
        )
    canonical_op_type = next(t for t, c in PROXY_MAP.items() if c is proxy_cls)
    data = proxy_cls.resolve_request(pk, request)
    has_invoice = data.get("has_invoice", False)

    officer = get_object_or_404(Entity, user=request.user)

    amount = Decimal("0.00")
    date = timezone.now().date()
    description = ""
    selected_category_id = None
    formset = None

    project = data["url_entity"]
    errors = []

    if request.method == "POST":
        date_str = request.POST.get("date", "")
        date = parse_date(date_str) if date_str else timezone.now().date()
        description = request.POST.get("description", "")
        cat = request.POST.get("category", "")
        selected_category_id = int(cat) if cat else None

        if has_invoice:
            formset = _build_formset(
                proxy_cls, data=request.POST, instance=Invoice(), project=project
            )

        is_formset_valid = True
        if formset and not formset.is_valid():
            is_formset_valid = False
            messages.error(request, _("Please check the items table for errors."))

        if is_formset_valid:
            try:
                with db_transaction.atomic():

                    if has_invoice and formset:
                        amount = sum(
                            (
                                f.cleaned_data["quantity"]
                                * f.cleaned_data["unit_price"]
                                for f in formset
                                if f.cleaned_data and not f.cleaned_data.get("DELETE")
                            ),
                            Decimal("0.00"),
                        )
                    else:
                        amount = Decimal(request.POST.get("amount") or "0")

                    op = proxy_cls.objects.create(
                        operation_type=canonical_op_type,
                        source=data["source_entity"],
                        destination=data["dest_entity"],
                        amount=amount,
                        date=date,
                        description=description,
                        officer=officer,
                    )

                    amount_paid = request.POST.get("amount_paid")
                    amount_paid = Decimal(amount_paid if amount_paid else "0")
                    can_pay = data.get("can_pay")
                    if can_pay:
                        if amount_paid > amount:
                            raise ValueError(
                                _(
                                    "Error: paid amount %(paid)s is more than the total %(total)s"
                                )
                                % {"paid": amount_paid, "total": amount}
                            )
                        if (
                            not data.get("is_partially_payable")
                            and amount_paid < amount
                        ):
                            raise ValueError(
                                _(
                                    "You can't pay less than %(amount)s for this operation."
                                )
                                % {"amount": amount}
                            )
                        if amount_paid > 0:
                            op.create_payment_transaction(
                                amount_paid,
                                officer,
                                date=request.POST.get("date") or timezone.now().date(),
                                description=_(
                                    "Instant payment for the operation %(op_type)s %(pk)s"
                                )
                                % {
                                    "op_type": op.operation_type,
                                    "pk": op.pk,
                                },
                            )

                    if formset:
                        invoice = Invoice.objects.create(operation=op)
                        bound_formset = _build_formset(
                            proxy_cls,
                            data=request.POST,
                            instance=invoice,
                            project=project,
                        )
                        bound_formset.is_valid()  # already validated; re-bind to saved instance
                        bound_formset.save()
                        _save_inventory(proxy_cls, bound_formset)

                messages.success(
                    request,
                    _("%(label)s recorded successfully.") % {"label": data["label"]},
                )
                return redirect("operation_detail_view", pk=op.pk)
            except Exception as e:
                traceback.print_exc()
                errors.append(str(e))
                messages.error(
                    request, _("Transaction Error: %(error)s") % {"error": str(e)}
                )
    else:
        if has_invoice:
            formset = _build_formset(proxy_cls, instance=Invoice(), project=project)

    entities = proxy_cls.get_related_entities(data["url_entity"], data)
    theme_color, theme_icon = data["theme_color"], data["theme_icon"]
    categories = FinancialCategory.objects.filter(
        parent_entity=data["url_entity"],
        category_type=proxy_cls.category_type,
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
        "has_invoice": has_invoice,
        "creates_assets": proxy_cls.creates_assets,
        "is_partially_payable": data.get("is_partially_payable"),
        "can_pay": data.get("can_pay"),
        "categories": categories,
        "selected_category_id": selected_category_id,
        "amount": amount if amount != Decimal("0.00") else "",
        "date": date,
        "description": description,
        "errors": errors,
    }

    return render(request, "app_operation/generic_form.html", context)
