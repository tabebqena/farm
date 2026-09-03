"""Birth-operation create view.

:class:`BirthCreateView` creates a :class:`BirthOperation`, typically adding one
or more new animals to the herd.
"""

from apps.app_base.logging_utils import logger
from apps.app_operation.models.proxies.op_birth import BirthOperation

from . import OperationCreateView


class BirthCreateView(OperationCreateView):
    """Create a birth operation that adds new animals to the herd."""

    proxy_cls = BirthOperation
    template_name = "app_operation/birth_form.html"

    def dispatch(self, request, *args, **kwargs):
        logger.debug(
            f"Setting up birth creation view | project_pk={kwargs.get('pk')} | "
            f"user={request.user.username}"
        )
        return super().dispatch(request, *args, **kwargs)
