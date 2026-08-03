from django.utils.decorators import method_decorator

from apps.app_base.debug import DebugContext, debug_view
from apps.app_operation.models.proxies.op_death import DeathOperation

from . import OperationCreateView


class DeathCreateView(OperationCreateView):
    proxy_cls = DeathOperation
    template_name = "app_operation/death_form.html"

    @method_decorator(debug_view)
    def dispatch(self, request, *args, **kwargs):
        with DebugContext.section(
            "Setting up death creation view",
            {
                "project_pk": kwargs.get("pk"),
                "user": request.user.username,
            },
        ):
            return super().dispatch(request, *args, **kwargs)
