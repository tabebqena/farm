from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity
from apps.app_operation.models.period import FinancialPeriod


@login_required
def period_detail_view(request, period_pk):
    period = get_object_or_404(
        FinancialPeriod,
        pk=period_pk,
        error_message="Financial period not found or has been deleted."
    )
    context = {
        "period": period,
        "entity": period.entity,
    }
    return render(request, "app_operation/period_detail.html", context)


@login_required
def period_list_view(request, entity_pk):
    entity = get_object_or_404(
        Entity,
        pk=entity_pk,
        error_message="Entity not found or has been deleted."
    )
    periods = entity.financial_periods.all().order_by("-start_date")
    context = {
        "entity": entity,
        "periods": periods,
    }
    return render(request, "app_operation/period_list.html", context)


@login_required
def period_create_view(request, entity_pk):
    entity = get_object_or_404(
        Entity,
        pk=entity_pk,
        error_message="Entity not found or has been deleted."
    )

    if request.method == "GET":
        context = {"entity": entity}
        return render(request, "app_operation/period_form.html", context)

    if request.method == "POST":
        try:
            start_date = request.POST.get("start_date")
            if not start_date:
                raise ValidationError(_("Start date is required."))

            period = FinancialPeriod(entity=entity, start_date=start_date)
            period.full_clean()
            period.save()
            return redirect("period_list_view", entity_pk=entity.pk)
        except ValidationError as e:
            context = {"entity": entity, "errors": e.messages}
            return render(request, "app_operation/period_form.html", context, status=400)


@login_required
def period_close_view(request, period_pk):
    period = get_object_or_404(
        FinancialPeriod,
        pk=period_pk,
        error_message="Financial period not found or has been deleted."
    )

    if period.end_date is not None:
        context = {
            "period": period,
            "errors": [_("This period is already closed.")],
        }
        return render(request, "app_operation/period_close.html", context, status=400)

    if request.method == "GET":
        context = {"period": period}
        return render(request, "app_operation/period_close.html", context)

    if request.method == "POST":
        try:
            end_date = request.POST.get("end_date")
            if not end_date:
                raise ValidationError(_("End date is required."))

            with transaction.atomic():
                period.close(end_date)
            return redirect("period_list_view", entity_pk=period.entity.pk)
        except ValidationError as e:
            context = {"period": period, "errors": e.messages}
            return render(request, "app_operation/period_close.html", context, status=400)
