import traceback
from decimal import Decimal
from typing import TYPE_CHECKING

from django.contrib import messages
from django.db import transaction as db_transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from django.views import View

from apps.app_inventory.forms import InvoiceItemCreateFormSet, InvoiceItemSelectFormSet
from apps.app_operation.models import FinancialCategory
from apps.app_operation.models.proxies import PROXY_MAP, get_canonical_type

if TYPE_CHECKING:
    from apps.app_operation.models.operation import Operation


# ---------------------------------------------------------------------------
# Module-level helpers (pure logic, no request/view state)
# ---------------------------------------------------------------------------

def _build_formset(proxy_cls, data=None, instance=None, project=None):
    """Return the correct formset class for this operation, bound or unbound."""
    if proxy_cls.creates_assets:
        return InvoiceItemCreateFormSet(data, instance=instance, project=project) if data is not None \
            else InvoiceItemCreateFormSet(instance=instance, project=project)
    return InvoiceItemSelectFormSet(data, instance=instance) if data is not None \
        else InvoiceItemSelectFormSet(instance=instance)


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------

class OperationCreateView(View):
    template_name = "app_operation/generic_form.html"

    # Declared here for type-checker visibility; assigned in dispatch() after guard.
    proxy_cls: "type[Operation]"
    canonical_op_type: str
    data: dict
    has_invoice: bool
    project: object

    # ---- lifecycle ----------------------------------------------------------

    def dispatch(self, request, *args, **kwargs):
        proxy_cls = get_canonical_type(kwargs["op_type"])
        if not proxy_cls:
            return HttpResponseBadRequest(
                _("Unsupported operation %(op_type)s") % {"op_type": kwargs["op_type"]}
            )
        # proxy_cls is narrowed to type[Operation] from here on
        self.proxy_cls = proxy_cls
        self.canonical_op_type = next(t for t, c in PROXY_MAP.items() if c is proxy_cls)
        self.data = proxy_cls.resolve_request(kwargs["pk"], request)
        self.has_invoice = self.data.get("has_invoice", False)
        self.project = self.data["url_entity"]
        return super().dispatch(request, *args, **kwargs)

    # ---- HTTP handlers ------------------------------------------------------

    def get(self, request, *args, **kwargs):
        formset = self._make_formset() if self.has_invoice else None
        return render(request, self.template_name, self._build_context(formset=formset))

    def post(self, request, *args, **kwargs):
        date, description, selected_category_id = self._parse_post_fields()
        formset = self._make_formset(data=request.POST) if self.has_invoice else None

        if formset and not formset.is_valid():
            messages.error(request, _("Please check the items table for errors."))
            return render(request, self.template_name, self._build_context(
                formset=formset, date=date, description=description,
                selected_category_id=selected_category_id,
            ))

        amount = Decimal("0.00")
        errors = []
        try:
            with db_transaction.atomic():
                amount = self._compute_amount(formset)
                op = self._create_operation(amount, date, description)
                self._process_payment(op, amount)
                if formset:
                    self._process_invoice(op)

            messages.success(
                request,
                _("%(label)s recorded successfully.") % {"label": self.data["label"]},
            )
            return redirect("operation_detail_view", pk=op.pk)

        except Exception as e:
            traceback.print_exc()
            errors.append(str(e))
            messages.error(request, _("Transaction Error: %(error)s") % {"error": str(e)})

        return render(request, self.template_name, self._build_context(
            formset=formset, amount=amount, date=date,
            description=description, selected_category_id=selected_category_id,
            errors=errors,
        ))

    # ---- business logic helpers ---------------------------------------------

    def _parse_post_fields(self):
        date_str = self.request.POST.get("date", "")
        cat = self.request.POST.get("category", "")
        return (
            parse_date(date_str) if date_str else timezone.now().date(),
            self.request.POST.get("description", ""),
            int(cat) if cat else None,
        )

    def _make_formset(self, data=None):
        from apps.app_operation.models.operation import Operation
        return _build_formset(self.proxy_cls, data=data, instance=Operation(), project=self.project)

    def _compute_amount(self, formset):
        if self.has_invoice and formset:
            return sum(
                (
                    f.cleaned_data["quantity"] * f.cleaned_data["unit_price"]
                    for f in formset
                    if f.cleaned_data and not f.cleaned_data.get("DELETE")
                ),
                Decimal("0.00"),
            )
        return Decimal(self.request.POST.get("amount") or "0")

    def _create_operation(self, amount, date, description):
        return self.proxy_cls.objects.create(
            operation_type=self.canonical_op_type,
            source=self.data["source_entity"],
            destination=self.data["dest_entity"],
            amount=amount,
            date=date,
            description=description,
            officer=self.request.user,
        )

    def _process_payment(self, op, amount):
        if not self.data.get("can_pay"):
            return
        amount_paid = Decimal(self.request.POST.get("amount_paid") or "0")
        if amount_paid > amount:
            raise ValueError(
                _("Error: paid amount %(paid)s is more than the total %(total)s")
                % {"paid": amount_paid, "total": amount}
            )
        if not self.data.get("is_partially_payable") and amount_paid < amount:
            raise ValueError(
                _("You can't pay less than %(amount)s for this operation.")
                % {"amount": amount}
            )
        if amount_paid > 0:
            op.create_payment_transaction(
                amount_paid,
                self.request.user,
                date=self.request.POST.get("date") or timezone.now().date(),
                description=_("Instant payment for the operation %(op_type)s %(pk)s")
                % {"op_type": op.operation_type, "pk": op.pk},
            )

    def _process_invoice(self, op):
        bound_formset = _build_formset(
            self.proxy_cls, data=self.request.POST, instance=op, project=self.project
        )
        bound_formset.is_valid()  # already validated; re-bind to saved instance
        bound_formset.save()
        op.save_inventory(bound_formset)

    def _build_context(self, *, formset, amount=Decimal("0.00"), date=None,
                       description="", selected_category_id=None, errors=None):
        categories = FinancialCategory.objects.filter(
            parent_entity=self.data["url_entity"],
            category_type=self.proxy_cls.category_type,
            is_active=True,
        )
        return {
            "primary": self.data["url_entity"],
            "config": self.data,
            "op_type": self.canonical_op_type,
            "today": timezone.now().date(),
            "entities": self.proxy_cls.get_related_entities(self.data["url_entity"], self.data),
            "theme_color": self.data["theme_color"],
            "theme_icon": self.data["theme_icon"],
            "formset": formset,
            "has_invoice": self.has_invoice,
            "creates_assets": self.proxy_cls.creates_assets,
            "is_partially_payable": self.data.get("is_partially_payable"),
            "can_pay": self.data.get("can_pay"),
            "categories": categories,
            "selected_category_id": selected_category_id,
            "amount": amount if amount != Decimal("0.00") else "",
            "date": date or timezone.now().date(),
            "description": description,
            "errors": errors or [],
        }
