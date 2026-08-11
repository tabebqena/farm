from django.contrib import messages
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _

from apps.app_base.debug import DebugContext, debug_view
from apps.app_operation.models.proxies.op_sale import SaleOperation

from . import OperationCreateView


class SaleCreateView(OperationCreateView):
    proxy_cls = SaleOperation
    template_name = "app_operation/sale_form.html"

    @method_decorator(debug_view)
    def dispatch(self, request, *args, **kwargs):
        with DebugContext.section(
            "Setting up sale creation view",
            {
                "project_pk": kwargs.get("pk"),
                "user": request.user.username,
            },
        ):
            return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Validate prerequisites before processing sale submission."""
        related_entities = self.proxy_cls.get_related_entities(self.project, self.data)
        if not related_entities:
            warning_msg = _(
                "This project has no active clients. "
                "Add a client before recording a sale."
            )
            DebugContext.warn(
                "No active clients found", {"project_id": self.project.pk}
            )
            DebugContext.audit(
                action="sale_creation_no_clients",
                entity_type="SaleOperation",
                entity_id=None,
                details={"project_id": self.project.pk},
                user=request.user.username,
            )
            messages.warning(request, warning_msg)
            return redirect("operation_list_view", person_pk=self.project.pk)
        return super().post(request, *args, **kwargs)

    def _build_context(self, **kwargs):
        # The source of a sale is the client (chosen on POST); the generic
        # form's fund balance falls back to the URL entity (the project) until
        # a client is selected, so no extra context is needed here.
        return super()._build_context(**kwargs)
