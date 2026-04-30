import json
import traceback
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.db import transaction as db_transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.decorators import method_decorator

from apps.app_base.debug import DebugContext, debug_view
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity
from apps.app_inventory.models import InvoiceItem, Product, ProductLedgerEntry
from apps.app_operation.models.proxies.op_capital_gain import CapitalGainOperation
from apps.app_operation.models.proxies.op_capital_loss import CapitalLossOperation

from .create import OperationCreateView


class EvaluationForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        label=_("Product"),
        empty_label=_("— Select a product —"),
    )
    new_unit_price = forms.DecimalField(
        label=_("New unit price"),
        min_value=Decimal("0.01"),
        max_digits=15,
        decimal_places=2,
    )
    date = forms.DateField(
        label=_("Date"),
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    description = forms.CharField(
        label=_("Notes"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project:
            self.fields["product"].queryset = (
                Product.objects.filter(product_template__entities=project)
                .select_related("product_template")
                .order_by("product_template__name", "pk")
            )
        if not self.data and "date" not in kwargs.get("initial", {}):
            self.fields["date"].initial = timezone.now().date()


class EvaluationCreateView(OperationCreateView):
    template_name = "app_operation/evaluation_form.html"

    @method_decorator(debug_view)
    def dispatch(self, request, *args, **kwargs):
        with DebugContext.section("Setting up evaluation creation view", {
            "project_pk": kwargs.get("pk"),
            "product_pk": kwargs.get("product_pk"),
            "user": request.user.username,
        }):
            self.project = get_object_or_404(
                Entity,
                pk=kwargs["pk"],
                error_message="Project not found or has been deleted."
            )
            DebugContext.success("Project loaded", {"project_id": self.project.pk})

            self.product_pk = kwargs.get("product_pk")
            if self.product_pk:
                self.product = get_object_or_404(
                    Product,
                    pk=self.product_pk,
                    error_message="Product not found or has been deleted."
                )
                DebugContext.success("Product loaded", {"product_id": self.product.pk})
            else:
                self.product = None
            from django.views import View

        return View.dispatch(self, request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        with DebugContext.section("Rendering evaluation form", {
            "project_id": self.project.pk,
            "product_pk": self.product_pk,
        }):
            initial = {"date": timezone.now().date()}
            if self.product:
                initial["product"] = self.product
            form = EvaluationForm(project=self.project, initial=initial)
            DebugContext.success("Form rendered", {"product_count": form.fields["product"].queryset.count()})
            return render(request, self.template_name, self._build_evaluation_context(form))

    def post(self, request, *args, **kwargs):
        with DebugContext.section("Processing product evaluation", {
            "project_id": self.project.pk,
            "user": request.user.username,
        }):
            form = EvaluationForm(request.POST, project=self.project)
            if not form.is_valid():
                error_details = {
                    "form_errors": str(form.errors),
                }
                DebugContext.warn("Evaluation form validation failed", error_details)
                DebugContext.audit(
                    action="evaluation_form_validation_failed",
                    entity_type="Evaluation",
                    entity_id=None,
                    details=error_details,
                    user=request.user.username
                )
                return render(
                    request, self.template_name, self._build_evaluation_context(form)
                )

            product = form.cleaned_data["product"]
            new_unit_price = form.cleaned_data["new_unit_price"]
            date = form.cleaned_data["date"]
            description = form.cleaned_data["description"]

            with DebugContext.section("Calculating valuation delta", {
                "product_id": product.pk,
                "new_unit_price": str(new_unit_price),
            }):
                quantity = product.quantity
                current_value = product.current_value
                current_unit_price = (current_value / quantity) if quantity else Decimal("0.00")
                delta = (new_unit_price - current_unit_price) * (quantity or 1)

                DebugContext.success("Valuation calculated", {
                    "quantity": quantity,
                    "current_unit_price": str(current_unit_price),
                    "new_unit_price": str(new_unit_price),
                    "delta": str(delta),
                })

            if abs(delta) < Decimal("0.01"):
                DebugContext.warn("No material change in valuation", {
                    "delta": str(delta),
                    "product_id": product.pk,
                })
                messages.info(request, _("No material change — no operation recorded."))
                return render(
                    request, self.template_name, self._build_evaluation_context(form)
                )

            self.proxy_cls = CapitalGainOperation if delta > 0 else CapitalLossOperation
            self._setup_view(self.kwargs["pk"], request)
            amount = abs(delta).quantize(Decimal("0.01"))

            try:
                with db_transaction.atomic():
                    with DebugContext.section("Creating evaluation operation", {
                        "operation_type": "CapitalGain" if delta > 0 else "CapitalLoss",
                        "amount": str(amount),
                    }):
                        op = self._create_operation(amount, date, description)
                        item = InvoiceItem.objects.create(
                            operation=op,
                            product=product.product_template,
                            quantity=Decimal(quantity) if quantity else Decimal("1"),
                            unit_price=abs(new_unit_price - current_unit_price),
                        )
                        product.validate_active()
                        product.invoice_items.add(item)
                        ProductLedgerEntry.record(op)
                        DebugContext.success("Evaluation operation created", {
                            "operation_id": op.pk,
                            "invoice_item_id": item.pk,
                        })

                direction = _("Capital Gain") if delta > 0 else _("Capital Loss")
                DebugContext.success("Evaluation recorded successfully", {
                    "operation_id": op.pk,
                    "direction": direction,
                    "amount": str(amount),
                })
                DebugContext.audit(
                    action="evaluation_recorded",
                    entity_type="Evaluation",
                    entity_id=op.pk,
                    details={
                        "operation_type": "CapitalGain" if delta > 0 else "CapitalLoss",
                        "product_id": product.pk,
                        "amount": str(amount),
                    },
                    user=request.user.username
                )
                messages.success(
                    request,
                    _("%(dir)s of %(amt)s recorded.") % {"dir": direction, "amt": amount},
                )
                return redirect("operation_detail_view", pk=op.pk)

            except Exception as e:
                traceback.print_exc()
                error_details = {
                    "exception_type": type(e).__name__,
                    "error_message": str(e),
                    "product_id": product.pk,
                }
                DebugContext.error("Evaluation operation creation failed", e, error_details)
                DebugContext.audit(
                    action="evaluation_creation_failed",
                    entity_type="Evaluation",
                    entity_id=None,
                    details=error_details,
                    user=request.user.username
                )
                messages.error(request, str(e))
                return render(
                    request,
                    self.template_name,
                    self._build_evaluation_context(form, errors=[str(e)]),
                )

    def _build_evaluation_context(self, form, errors=None):
        product_data = {}

        for p in form.fields["product"].queryset:
            cv = p.current_value
            q = p.quantity
            product_data[p.pk] = {
                "name": str(p.product_template),
                "quantity": q,
                "unit": p.product_template.default_unit,
                "current_value": float(cv),
                "current_unit_price": float(cv / q) if q else 0.0,
            }
        return {
            "primary": self.project,
            "form": form,
            "today": timezone.now().date(),
            "product_data_json": json.dumps(product_data),
            "product_pk": self.product_pk,
            "errors": errors or [],
        }
