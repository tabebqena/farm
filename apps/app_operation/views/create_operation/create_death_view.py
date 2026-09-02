"""Death-operation create view.

:class:`DeathCreateView` creates a :class:`DeathOperation` for an individual
animal.
"""

from apps.app_base.logging_utils import logger
from apps.app_operation.models.proxies.op_death import DeathOperation

from . import OperationCreateView


class DeathCreateView(OperationCreateView):
    proxy_cls = DeathOperation
    template_name = "app_operation/death_form.html"

    def dispatch(self, request, *args, **kwargs):
        logger.debug(
            f"Setting up death creation view | project_pk={kwargs.get('pk')} | "
            f"user={request.user.username}"
        )
        return super().dispatch(request, *args, **kwargs)
