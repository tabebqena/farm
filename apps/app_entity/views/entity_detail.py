from apps.app_entity.models import Entity
from django.shortcuts import get_object_or_404, render


def entity_detail_view(request, pk):
    # Fetch entity with all its identity links and fund in one hit
    entity = get_object_or_404(
        Entity.objects.select_related("person", "project", "fund", "user"),
        pk=pk,
    )

    # Categorize stakeholders for the UI
    stakeholders = entity.stakeholders.all().select_related("person", "project", "fund")

    context = {
        "entity": entity,
        # "vendors": stakeholders.filter(is_vendor=True),
        # "workers": stakeholders.filter(is_worker=True),
        # "clients": stakeholders.filter(is_client=True),
        # "shareholders": stakeholders.filter(is_shareholder=True),
        # You would later add transaction history here:
        # 'transactions': entity.fund.transactions.all().order_by('-timestamp')[:10]
    }

    return render(request, "app_entity/entity_detail.html", context)
