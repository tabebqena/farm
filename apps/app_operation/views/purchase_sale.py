from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from django.views import View
from django.utils.decorators import method_decorator

from apps.app_base.debug import DebugContext, debug_view
from apps.app_operation.models.proxies.op_birth import BirthOperation
from apps.app_operation.models.proxies.op_death import DeathOperation
from apps.app_operation.models.proxies.op_purchase import PurchaseOperation
from apps.app_operation.models.proxies.op_sale import SaleOperation

from .create import OperationCreateView


class PurchaseCreateView(OperationCreateView):
    proxy_cls = PurchaseOperation
    template_name = "app_operation/purchase_form.html"

    @method_decorator(debug_view)
    def dispatch(self, request, *args, **kwargs):
        with DebugContext.section("Setting up purchase creation view", {
            "project_pk": kwargs.get("pk"),
            "user": request.user.username,
        }):
            self._setup_view(kwargs["pk"], request)
            related_entities = self.proxy_cls.get_related_entities(self.project, self.data)
            if not related_entities:
                warning_msg = _("This project has no active vendors. Add a vendor before recording a purchase.")
                DebugContext.warn("No active vendors found", {"project_id": self.project.pk})
                DebugContext.audit(
                    action="purchase_creation_no_vendors",
                    entity_type="PurchaseOperation",
                    entity_id=None,
                    details={"project_id": self.project.pk},
                    user=request.user.username
                )
                messages.warning(request, warning_msg)
                return redirect("operation_list_view", person_pk=self.project.pk)
            DebugContext.success("Vendors found", {"vendor_count": len(related_entities) if isinstance(related_entities, (list, tuple)) else "multiple"})
        return View.dispatch(self, request, *args, **kwargs)

    def _build_context(self, **kwargs):
        ctx = super()._build_context(**kwargs)
        ctx["project_balance"] = self.project.balance
        return ctx


class SaleCreateView(OperationCreateView):
    proxy_cls = SaleOperation
    template_name = "app_operation/sale_form.html"

    @method_decorator(debug_view)
    def dispatch(self, request, *args, **kwargs):
        with DebugContext.section("Setting up sale creation view", {
            "project_pk": kwargs.get("pk"),
            "user": request.user.username,
        }):
            self._setup_view(kwargs["pk"], request)
            related_entities = self.proxy_cls.get_related_entities(self.project, self.data)
            if not related_entities:
                warning_msg = _("This project has no active clients. Add a client before recording a sale.")
                DebugContext.warn("No active clients found", {"project_id": self.project.pk})
                DebugContext.audit(
                    action="sale_creation_no_clients",
                    entity_type="SaleOperation",
                    entity_id=None,
                    details={"project_id": self.project.pk},
                    user=request.user.username
                )
                messages.warning(request, warning_msg)
                return redirect("operation_list_view", person_pk=self.project.pk)
            DebugContext.success("Clients found", {"client_count": len(related_entities) if isinstance(related_entities, (list, tuple)) else "multiple"})
        return View.dispatch(self, request, *args, **kwargs)

    def _build_context(self, **kwargs):
        ctx = super()._build_context(**kwargs)
        ctx["project_balance"] = self.project.balance
        return ctx


class BirthCreateView(OperationCreateView):
    proxy_cls = BirthOperation
    template_name = "app_operation/birth_form.html"

    @method_decorator(debug_view)
    def dispatch(self, request, *args, **kwargs):
        with DebugContext.section("Setting up birth creation view", {
            "project_pk": kwargs.get("pk"),
            "user": request.user.username,
        }):
            self._setup_view(kwargs["pk"], request)
            DebugContext.success("Birth view setup complete", {"project_id": self.project.pk})
        return View.dispatch(self, request, *args, **kwargs)


class DeathCreateView(OperationCreateView):
    proxy_cls = DeathOperation
    template_name = "app_operation/death_form.html"

    @method_decorator(debug_view)
    def dispatch(self, request, *args, **kwargs):
        with DebugContext.section("Setting up death creation view", {
            "project_pk": kwargs.get("pk"),
            "user": request.user.username,
        }):
            self._setup_view(kwargs["pk"], request)
            DebugContext.success("Death view setup complete", {"project_id": self.project.pk})
        return View.dispatch(self, request, *args, **kwargs)
