"""Operation list view.

:class:`OperationListView` renders the paginated, filterable list of operations
for an entity.
"""

from django.conf import settings
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.shortcuts import render
from django.views import View

from apps.app_base.logging_utils import logger
from apps.app_base.navigation import set_entity_navigation
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity
from apps.app_operation.models.operation import Operation
from apps.app_operation.models.proxies import PROXY_MAP


class OperationListView(View):
    """List all operations involving a person."""

    def get(self, request, *args, **kwargs):
        person_pk = kwargs["person_pk"]
        logger.debug(
            f"Fetching entity for operation listing | entity_pk={person_pk} | "
            f"user={request.user.username}"
        )
        entity_person = get_object_or_404(
            Entity,
            pk=person_pk,
            error_message="Entity not found or has been deleted."
        )
        logger.debug(
            f"Entity loaded | entity_id={entity_person.id} | entity_name={entity_person.name}"
        )

        logger.debug(f"Fetching operations involving entity | entity_id={entity_person.id}")
        all_operations = (
            Operation.objects.filter(Q(source=entity_person) | Q(destination=entity_person))
            .order_by("-date", "-created_at")
        )
        logger.debug(f"Operations query executed | count={all_operations.count()}")

        proxy_operations = [
            PROXY_MAP.get(op.operation_type, Operation).objects.get(pk=op.pk)
            for op in all_operations
        ]
        logger.debug(
            f"Operations loaded | count={len(proxy_operations)} | "
            f"entity_id={entity_person.id}"
        )

        # Precompute user-friendly settlement values for the list template.
        # The kind (one_shot / paid / repayed) and paid/remaining/percent are
        # computed by Operation.settlement_summary().
        operations = [
            {"operation": op, **op.settlement_summary()} for op in proxy_operations
        ]

        paginator = Paginator(operations, 25)
        page_number = request.GET.get('page', 1)
        try:
            page_obj = paginator.page(page_number)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)

        # Replace the ambiguous "Entity" navigation label with the entity's display name
        set_entity_navigation(request, entity_person)

        context = {
            "entity_person": entity_person,
            "operations": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": paginator,
            "balance": entity_person.balance,
            "currency": getattr(settings, "CURRENCY_SYMBOL", "$"),
        }
        return render(request, "app_operation/operation_list.html", context)
