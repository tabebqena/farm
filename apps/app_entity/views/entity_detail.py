from django.shortcuts import render

from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity


def entity_detail_view(request, pk):
    # Fetch entity with all its identity links and fund in one hit
    entity = get_object_or_404(
        Entity,
        pk=pk,
        error_message="Entity not found or has been deleted."
    )

    context = {
        "entity": entity,
        # "vendors": stakeholders.filter(is_vendor=True),
        # "workers": stakeholders.filter(is_worker=True),
        # "clients": stakeholders.filter(is_client=True),
        # "shareholders": stakeholders.filter(is_shareholder=True),
        # You would later add transaction history here:
        # 'transactions': entity.transactions.all().order_by('-timestamp')[:10]
    }

    return render(request, "app_entity/entity_detail.html", context)
