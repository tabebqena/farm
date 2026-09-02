"""Entity detail view.

:class:`EntityDetailView` shows a single entity together with its financial
summary — current payables, receivables and inventory value.
"""

from datetime import date

from django.conf import settings
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.app_base.logging_utils import logger
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.stock import inventory_value


class EntityDetailView(View):
    """Display entity detail page."""

    def get(self, request, *args, **kwargs):
        pk = kwargs["pk"]
        logger.debug(
            f"Fetching entity details | entity_pk={pk} | user={request.user.username}"
        )
        entity = get_object_or_404(
            Entity,
            pk=pk,
            error_message="Entity not found or has been deleted."
        )
        logger.debug(
            f"Entity loaded | entity_id={entity.id} | entity_type={entity.entity_type} | "
            f"entity_name={entity.name}"
        )

        edit_view = 'project_edit' if entity.entity_type == EntityType.PROJECT else 'person_edit'
        request.navigation_overrides = {
            'related_urls': {
                'Edit': reverse(edit_view, kwargs={'pk': entity.pk}),
            }
        }

        logger.debug(f"Computing entity financial summary | entity_id={entity.id}")
        payables = entity.payables
        receivables = entity.receivables
        stock_value = inventory_value(entity, date.today())
        logger.debug(
            f"Financial summary computed | payables={payables} | receivables={receivables} | "
            f"stock_value={stock_value}"
        )

        context = {
            "entity": entity,
            "payables": payables,
            "receivables": receivables,
            "stock_value": stock_value,
            "currency": getattr(settings, "CURRENCY_SYMBOL", "$"),
        }

        return render(request, "app_entity/entity_detail.html", context)
