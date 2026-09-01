import traceback
from decimal import Decimal
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib import messages
from django.db import transaction as db_transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View

from apps.app_base.logging_utils import audit_logger, logger
from apps.app_entity.models.category import (
    FinancialCategory,
)
from apps.app_inventory.forms import InvoiceItemCreateFormSet, InvoiceItemSelectFormSet
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import PROXY_MAP, get_canonical_type
from apps.app_operation.validators import OperationDataValidator

if TYPE_CHECKING:
    from apps.app_operation.models.operation import Operation


# ---------------------------------------------------------------------------
# Module-level helpers (pure logic, no request/view state)
# ---------------------------------------------------------------------------


def _build_formset(proxy_cls, data=None, instance=None, project=None, is_birth=False):
    """Return the correct formset class for this operation, bound or unbound."""
    if proxy_cls.creates_assets:
        return (
            InvoiceItemCreateFormSet(
                data, instance=instance, project=project, is_birth=is_birth
            )
            if data is not None
            else InvoiceItemCreateFormSet(
                instance=instance, project=project, is_birth=is_birth
            )
        )
    return (
        InvoiceItemSelectFormSet(data, instance=instance)
        if data is not None
        else InvoiceItemSelectFormSet(instance=instance)
    )


def _compute_amount(has_invoice, formset, raw_amount):
    """Compute the operation amount from the formset or raw POST value."""
    if has_invoice and formset:
        return sum(
            (
                f.cleaned_data["quantity"] * f.cleaned_data["unit_price"]
                for f in formset
                if f.cleaned_data and not f.cleaned_data.get("DELETE")
            ),
            Decimal("0.00"),
        )
    return Decimal(raw_amount or "0")


# TODO display error if the selected operation will not proceed
# no system or world entity while the operation requires
# no project shared in while the project required
# no assigned worker, vendor, client, shareholder & the operaytoion requires
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

    def _setup_view(self, pk, request):
        # A proxy may serve multiple operation types (e.g. CorrectionOperation
        # serves both CORRECTION_CREDIT and CORRECTION_DEBIT), so resolve the
        # canonical type from the URL slug when the proxy supports it; otherwise
        # fall back to the single-type class match.
        resolver = getattr(self.proxy_cls, "operation_type_for_url", None)
        url_op_type = getattr(self, "url_op_type", None)
        if resolver is not None and url_op_type:
            self.canonical_op_type = resolver(url_op_type)
        else:
            self.canonical_op_type = next(
                t for t, c in PROXY_MAP.items() if c is self.proxy_cls
            )
        self.data = self.proxy_cls.resolve_request(
            pk, request, operation_type=self.canonical_op_type
        )
        self.has_invoice = self.data.get("has_invoice", False)
        self.project = self.data["url_entity"]

    def dispatch(self, request, *args, **kwargs):
        logger.debug(
            f"Setting up operation creation view | op_type={kwargs.get('op_type')} | "
            f"pk={kwargs.get('pk')} | user={request.user.username}"
        )
        # Resolve proxy_cls from URL when present; otherwise rely on
        # the class attribute set on dedicated child views (Birth, Death, Sale).
        op_type = kwargs.get("op_type")
        if op_type:
            proxy_cls = get_canonical_type(op_type)
            if not proxy_cls:
                error_msg = _("Unsupported operation %(op_type)s") % {
                    "op_type": op_type
                }
                logger.error(f"{error_msg} | op_type={op_type}")
                audit_logger.info(
                    f"invalid_operation_type | Operation:None | "
                    f"user={request.user.username} | op_type={op_type}"
                )
                return HttpResponseBadRequest(error_msg)
            self.proxy_cls = proxy_cls
            # Remember the URL slug so multi-type proxies can resolve the
            # canonical operation type in _setup_view.
            self.url_op_type = op_type
        # else: proxy_cls already set as class attribute on child class

        self._setup_view(kwargs["pk"], request)
        # SALE is only created through the sale wizard — the generic create
        # view must not offer a second, divergent sale path.
        from apps.app_operation.models.proxies import SaleOperation

        if self.proxy_cls is SaleOperation:
            return redirect("sale_wizard_step1", pk=kwargs["pk"])
        logger.debug(f"View setup complete | op_type={self.canonical_op_type}")
        return super().dispatch(request, *args, **kwargs)

    # ---- HTTP handlers ------------------------------------------------------

    def get(self, request, *args, **kwargs):
        logger.debug(
            f"Rendering operation creation form | op_type={self.canonical_op_type} | "
            f"has_invoice={self.has_invoice}"
        )
        formset = self._make_formset()
        logger.debug(f"Form rendered | formset_count={len(formset) if formset else 0}")
        return render(
            request, self.template_name, self._build_context(formset=formset)
        )

    def post(self, request, *args, **kwargs):
        logger.debug(
            f"Processing operation creation | op_type={self.canonical_op_type} | "
            f"user={request.user.username}"
        )
        # ── 1. Validate POST data via standalone validator ────────────
        parsed, error_response = self._validate_post(request)
        if error_response:
            return error_response

        date_val = parsed.date
        description = parsed.description
        selected_category_id = parsed.selected_category_id

        # ── 2. Create & validate formset ──────────────────────────────
        formset = self._make_formset(data=request.POST)
        error_response = self._validate_formset(
            request,
            formset,
            date=date_val,
            description=description,
            selected_category_id=selected_category_id,
        )
        if error_response:
            return error_response

        # ── 3. Compute amount ─────────────────────────────────────────
        amount = _compute_amount(
            self.has_invoice,
            formset,
            request.POST.get("amount"),
        )

        # ── 4. Delegate to model layer ────────────────────────────────
        response, errors = self._create_operation(
            request,
            parsed,
            amount=amount,
            date=date_val,
            description=description,
            selected_category_id=selected_category_id,
        )
        if response is not None:
            return response

        return self._render_with_errors(
            request,
            formset=formset,
            amount=amount,
            date=date_val,
            description=description,
            selected_category_id=selected_category_id,
            errors=errors,
        )

    def _validate_post(self, request):
        """Validate the raw POST data via the standalone validator.

        Returns ``(parsed, None)`` on success, or ``(None, error_response)``
        when validation failed (the error form was already rendered)."""
        validator = OperationDataValidator(request.POST, self.data)
        try:
            parsed = validator.validate()
        except Exception as e:
            logger.warning(f"POST data validation failed | error={e}")
            return None, self._render_with_errors(
                request,
                formset=self._make_formset(data=request.POST),
                errors=[str(e)],
                message=str(e),
            )
        return parsed, None

    def _validate_formset(
        self,
        request,
        formset,
        *,
        date,
        description,
        selected_category_id,
    ):
        """Return an error response when the formset is invalid, else ``None``."""
        if formset and not formset.is_valid():
            error_msg = _("Please check the items table for errors.")
            logger.warning(
                f"Formset validation failed | "
                f"formset_errors={formset.errors if formset else None} | "
                f"has_invoice={self.has_invoice}"
            )
            audit_logger.info(
                f"operation_formset_validation_failed | Operation:None | "
                f"user={request.user.username} | "
                f"formset_errors={str(formset.errors) if formset else None}"
            )
            return self._render_with_errors(
                request,
                formset=formset,
                date=date,
                description=description,
                selected_category_id=selected_category_id,
                message=error_msg,
            )
        return None

    def _create_operation(
        self,
        request,
        parsed,
        *,
        amount,
        date,
        description,
        selected_category_id,
    ):
        """Delegate to the model layer inside an atomic block.

        Returns ``(redirect_response, errors)`` on success, or
        ``(None, [errors])`` when creation raised (the caller re-renders)."""
        errors = []
        try:
            with db_transaction.atomic():
                logger.debug(
                    f"Creating operation transaction | op_type={self.canonical_op_type} | "
                    f"date={date}"
                )
                op = self.proxy_cls.create(
                    operation_type=self.canonical_op_type,
                    source=self.data["source_entity"],
                    destination=self.data["dest_entity"],
                    amount=amount,
                    date=date,
                    description=description,
                    officer=request.user,
                    amount_paid=parsed.amount_paid,
                    raw_post=request.POST,
                    project=self.project,
                    category_id=selected_category_id,
                )
                logger.debug(
                    f"Operation created | operation_id={op.pk} | amount={amount}"
                )

            logger.debug(
                f"Operation saved successfully | operation_id={op.pk} | "
                f"operation_type={op.operation_type}"
            )
            audit_logger.info(
                f"operation_created | Operation:{op.pk} | "
                f"user={request.user.username} | operation_type={op.operation_type} | "
                f"amount={amount} | date={date}"
            )
            messages.success(
                request,
                _("%(label)s recorded successfully.")
                % {"label": self.data["label"]},
            )
            return redirect("operation_detail_view", pk=op.pk), errors

        except Exception as e:
            traceback.print_exc()
            errors.append(str(e))
            error_details = {
                "exception_type": type(e).__name__,
                "error_message": str(e),
                "op_type": self.canonical_op_type,
            }
            logger.error(
                f"Operation creation failed | "
                f"exception_type={error_details['exception_type']} | "
                f"error_message={error_details['error_message']} | "
                f"op_type={self.canonical_op_type}"
            )
            audit_logger.error(
                f"operation_creation_failed | Operation:None | "
                f"user={request.user.username} | error={error_details}"
            )
            messages.error(
                request, _("Transaction Error: %(error)s") % {"error": str(e)}
            )
            return None, errors

    # ---- view helpers (no business logic) -----------------------------------

    def _make_formset(self, data=None, instance=None):
        if not self.has_invoice:
            return None
        return _build_formset(
            self.proxy_cls,
            data=data,
            instance=instance or self.proxy_cls(),
            project=self.project,
            is_birth=self.canonical_op_type == OperationType.BIRTH,
        )

    def _render_with_errors(
        self,
        request,
        formset,
        *,
        errors=None,
        message=None,
        **overrides
    ):
        """Render the create form with an error message and context overrides."""
        if message:
            messages.error(request, message)
        return render(
            request,
            self.template_name,
            self._build_context(formset=formset, errors=errors or [], **overrides),
        )

    def _build_context(
        self,
        *,
        formset,
        amount=Decimal("0.00"),
        date=None,
        description="",
        selected_category_id=None,
        errors=None
    ):
        categories = []
        if self.proxy_cls.has_category:
            categories = FinancialCategory.objects.filter(
                entities_relations__entity=self.data["url_entity"],
                entities_relations__is_active=True,
                category_type=self.proxy_cls.category_type,
            )
        # The entity whose fund backs this operation. When the source role is
        # "url" this is the project itself; for "post"/"system"/"world" source
        # roles the source is only known after the secondary entity is chosen,
        # so fall back to the URL (primary) entity until then.
        source_entity = self.data["source_entity"] or self.data["url_entity"]
        return {
            "primary": self.data["url_entity"],
            "config": self.data,
            "source_entity": source_entity,
            "source_balance": source_entity.balance,
            "currency": getattr(settings, "CURRENCY_SYMBOL", "$"),
            "op_type": self.canonical_op_type,
            "today": timezone.now().date(),
            "entities": self.proxy_cls.get_related_entities(
                self.data["url_entity"], self.data
            ),
            "secondary_entity": self.data["secondary_entity"],
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
