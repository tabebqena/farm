from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from django.views import View

from apps.app_operation.models.proxies.op_birth import BirthOperation
from apps.app_operation.models.proxies.op_death import DeathOperation
from apps.app_operation.models.proxies.op_purchase import PurchaseOperation
from apps.app_operation.models.proxies.op_sale import SaleOperation

from .create import OperationCreateView


class PurchaseCreateView(OperationCreateView):
    proxy_cls = PurchaseOperation
    template_name = "app_operation/purchase_form.html"

    def dispatch(self, request, *args, **kwargs):
        self._setup_view(kwargs["pk"], request)
        if not self.proxy_cls.get_related_entities(self.project, self.data):
            messages.warning(
                request,
                _("This project has no active vendors. Add a vendor before recording a purchase."),
            )
            return redirect("operation_list_view", person_pk=self.project.pk)
        return View.dispatch(self, request, *args, **kwargs)

    def _build_context(self, **kwargs):
        ctx = super()._build_context(**kwargs)
        ctx["project_balance"] = self.project.balance
        return ctx


class SaleCreateView(OperationCreateView):
    proxy_cls = SaleOperation
    template_name = "app_operation/sale_form.html"

    def dispatch(self, request, *args, **kwargs):
        self._setup_view(kwargs["pk"], request)
        if not self.proxy_cls.get_related_entities(self.project, self.data):
            messages.warning(
                request,
                _("This project has no active clients. Add a client before recording a sale."),
            )
            return redirect("operation_list_view", person_pk=self.project.pk)
        return View.dispatch(self, request, *args, **kwargs)

    def _build_context(self, **kwargs):
        ctx = super()._build_context(**kwargs)
        ctx["project_balance"] = self.project.balance
        return ctx


class BirthCreateView(OperationCreateView):
    proxy_cls = BirthOperation
    template_name = "app_operation/birth_form.html"

    def dispatch(self, request, *args, **kwargs):
        self._setup_view(kwargs["pk"], request)
        return View.dispatch(self, request, *args, **kwargs)


class DeathCreateView(OperationCreateView):
    proxy_cls = DeathOperation
    template_name = "app_operation/death_form.html"

    def dispatch(self, request, *args, **kwargs):
        self._setup_view(kwargs["pk"], request)
        return View.dispatch(self, request, *args, **kwargs)
