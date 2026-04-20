from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.forms import (
    InvoiceItemCreateFormSet,
    InventoryMovementLineFormSet,
)
from apps.app_inventory.models import InventoryMovement
from apps.app_operation.forms import PurchaseWizardStep1Form
from apps.app_operation.models import PurchaseOperation

STEPS = {
    1: {"name": "Basic Info", "title": _("Purchase — Basic Information")},
    2: {"name": "Invoice Items", "title": _("Purchase — Invoice Items")},
    3: {"name": "Payment", "title": _("Purchase — Payment (optional)")},
    4: {"name": "Goods Receipt", "title": _("Purchase — Goods Receipt (optional)")},
}


def purchase_wizard_view(request, pk, operation_pk=None, step=1):
    """Multi-step purchase wizard."""

    # Validate step number
    if step not in STEPS:
        messages.error(request, _("Invalid wizard step."))
        return redirect("operation_list_view", person_pk=pk)

    # Load project
    project = get_object_or_404(Entity, pk=pk, entity_type=EntityType.PROJECT)

    # Guard: project must have at least one active vendor
    vendor_count = Stakeholder.objects.filter(
        parent=project,
        role=StakeholderRole.VENDOR,
        active=True,
    ).count()
    if vendor_count == 0:
        messages.warning(
            request,
            _("Cannot create purchase: no active vendors configured for this project."),
        )
        return redirect("operation_list_view", person_pk=pk)

    # Load operation if provided (steps 2–4)
    operation = None
    if operation_pk:
        operation = get_object_or_404(PurchaseOperation, pk=operation_pk)
        if operation.source != project:
            messages.error(
                request, _("Operation does not belong to this project.")
            )
            return redirect("operation_list_view", person_pk=pk)

    # Guard: steps 2+ require operation_pk or session key (step 1 initial data)
    session_key = f"purchase_wizard_{project.pk}"
    if step >= 2 and not operation_pk:
        if session_key not in request.session:
            messages.error(
                request, _("Session expired. Please start from the beginning.")
            )
            return redirect("purchase_wizard_step1", pk=pk)

    # Dispatch
    if request.method == "POST":
        if step == 1:
            return _handle_step_1_post(request, project, operation)
        elif step == 2:
            return _handle_step_2_post(request, project, operation)
        elif step == 3:
            return _handle_step_3_post(request, project, operation)
        elif step == 4:
            return _handle_step_4_post(request, project, operation)

    # GET: build context and render
    context = {
        "project": project,
        "step": step,
        "steps": STEPS,
        "current_step": STEPS[step],
    }

    if step == 1:
        context.update(_get_step_1_context(request, project, operation))
    elif step == 2:
        context.update(_get_step_2_context(request, project, operation))
    elif step == 3:
        context.update(_get_step_3_context(request, project, operation))
    elif step == 4:
        context.update(_get_step_4_context(request, project, operation))

    return render(request, "app_operation/purchase_wizard.html", context)


# Step 1 handlers


def _get_step_1_context(request, project, operation=None):
    """Render Step 1: basic info form."""
    session_key = f"purchase_wizard_{project.pk}"

    if operation:
        # Back navigation to existing operation
        initial = {
            "date": operation.date,
            "vendor": operation.destination.pk,
            "description": operation.description,
        }
    else:
        # New purchase
        session_data = request.session.get(session_key, {})
        initial = {
            "date": session_data.get("date", date.today().isoformat()),
            "vendor": session_data.get("vendor_id"),
            "description": session_data.get("description", ""),
        }

    form = PurchaseWizardStep1Form(
        initial=initial,
        project=project,
    )

    # If editing existing operation, disable vendor (immutable)
    if operation:
        form.fields["vendor"].disabled = True
        form.fields["vendor"].help_text = "Vendor cannot be changed after items are entered."

    return {"form": form}


def _handle_step_1_post(request, project, operation=None):
    """Handle Step 1 POST: validate and store to session, or update existing operation."""
    session_key = f"purchase_wizard_{project.pk}"

    form = PurchaseWizardStep1Form(request.POST, project=project)

    if not form.is_valid():
        context = {
            "project": project,
            "step": 1,
            "steps": STEPS,
            "current_step": STEPS[1],
            "form": form,
        }
        if operation:
            context["operation"] = operation
        return render(
            request,
            "app_operation/purchase_wizard.html",
            context,
        )

    # If editing existing operation, update it (except vendor which is immutable)
    if operation:
        operation.date = form.cleaned_data["date"]
        operation.description = form.cleaned_data["description"]
        operation.save()
        messages.success(request, _("Basic information updated."))
        return redirect(
            "purchase_wizard_step",
            pk=project.pk,
            operation_pk=operation.pk,
            step=2,
        )

    # New purchase: store to session
    request.session[session_key] = {
        "date": form.cleaned_data["date"].isoformat(),
        "vendor_id": form.cleaned_data["vendor"].pk,
        "description": form.cleaned_data["description"],
    }
    request.session.modified = True

    messages.success(request, _("Basic information saved. Now add invoice items."))
    return redirect("purchase_wizard_step2_new", pk=project.pk)


# Step 2 handlers


def _get_step_2_context(request, project, operation):
    """Render Step 2: invoice items formset."""
    if operation:
        formset = InvoiceItemCreateFormSet(instance=operation, project=project)
        step1_data = {
            "date": operation.date.isoformat(),
            "vendor": operation.destination,
            "description": operation.description,
        }
    else:
        formset = InvoiceItemCreateFormSet(
            instance=PurchaseOperation(), project=project
        )
        session_key = f"purchase_wizard_{project.pk}"
        step1_data = request.session.get(session_key, {})

    return {
        "formset": formset,
        "step1_data": step1_data,
    }


def _handle_step_2_post(request, project, operation):
    """Handle Step 2 POST: create Operation with invoice items."""
    session_key = f"purchase_wizard_{project.pk}"

    if not operation and session_key not in request.session:
        messages.error(
            request, _("Session expired. Please start from the beginning.")
        )
        return redirect("purchase_wizard_step1", pk=project.pk)

    # Get step 1 data
    if operation:
        step1_data = {
            "date": operation.date,
            "vendor": operation.destination,
            "description": operation.description,
        }
    else:
        session_data = request.session.get(session_key, {})
        from datetime import datetime

        step1_data = {
            "date": datetime.fromisoformat(session_data["date"]).date(),
            "vendor": get_object_or_404(Entity, pk=session_data["vendor_id"]),
            "description": session_data["description"],
        }

    # Validate formset (with unsaved instance)
    formset = InvoiceItemCreateFormSet(
        request.POST, instance=PurchaseOperation(), project=project
    )

    if not formset.is_valid():
        return render(
            request,
            "app_operation/purchase_wizard.html",
            {
                "project": project,
                "step": 2,
                "steps": STEPS,
                "current_step": STEPS[2],
                "formset": formset,
                "step1_data": step1_data,
            },
        )

    # Compute amount from formset rows
    amount = Decimal("0")
    for form in formset.forms:
        if form.cleaned_data and not form.cleaned_data.get("DELETE"):
            qty = form.cleaned_data.get("quantity") or Decimal("0")
            price = form.cleaned_data.get("unit_price") or Decimal("0")
            amount += qty * price

    if amount == 0:
        messages.error(request, _("Total amount must be greater than zero."))
        return render(
            request,
            "app_operation/purchase_wizard.html",
            {
                "project": project,
                "step": 2,
                "steps": STEPS,
                "current_step": STEPS[2],
                "formset": formset,
                "step1_data": step1_data,
            },
        )

    # Atomic: create operation and save invoice items
    try:
        with transaction.atomic():
            op = PurchaseOperation.objects.create(
                source=project,
                destination=step1_data["vendor"],
                amount=amount,
                date=step1_data["date"],
                description=step1_data["description"],
                officer=request.user,
                operation_type="PURCHASE",
            )

            # Re-bind formset to saved operation and save
            bound_formset = InvoiceItemCreateFormSet(
                request.POST, instance=op, project=project
            )
            bound_formset.is_valid()
            bound_formset.save()

            # Create Product instances
            op.save_inventory(bound_formset)

    except Exception as e:
        messages.error(
            request,
            _("Error creating operation: %(error)s") % {"error": str(e)},
        )
        return render(
            request,
            "app_operation/purchase_wizard.html",
            {
                "project": project,
                "step": 2,
                "steps": STEPS,
                "current_step": STEPS[2],
                "formset": formset,
                "step1_data": step1_data,
            },
        )

    # Clean up session
    if session_key in request.session:
        del request.session[session_key]
        request.session.modified = True

    messages.success(
        request,
        _("Invoice items saved. You can now record payment (optional)."),
    )
    return redirect("purchase_wizard_step", pk=project.pk, operation_pk=op.pk, step=3)


# Step 3 handlers


def _get_step_3_context(request, project, operation):
    """Render Step 3: optional cash payment."""
    return {
        "operation": operation,
        "amount_remaining": operation.amount_remaining_to_settle,
    }


def _handle_step_3_post(request, project, operation):
    """Handle Step 3 POST: optional payment transaction."""
    amount_paid_str = request.POST.get("amount_paid", "").strip()

    # If blank or zero, skip
    if not amount_paid_str or amount_paid_str == "0":
        messages.info(request, _("Skipped payment recording."))
        return redirect(
            "purchase_wizard_step",
            pk=project.pk,
            operation_pk=operation.pk,
            step=4,
        )

    # Parse amount
    try:
        amount_paid = Decimal(amount_paid_str)
    except Exception:
        messages.error(request, _("Invalid payment amount."))
        return render(
            request,
            "app_operation/purchase_wizard.html",
            {
                "project": project,
                "step": 3,
                "steps": STEPS,
                "current_step": STEPS[3],
                "operation": operation,
                "amount_remaining": operation.amount_remaining_to_settle,
            },
        )

    # Validate
    if amount_paid <= 0:
        messages.error(request, _("Payment amount must be greater than zero."))
        return render(
            request,
            "app_operation/purchase_wizard.html",
            {
                "project": project,
                "step": 3,
                "steps": STEPS,
                "current_step": STEPS[3],
                "operation": operation,
                "amount_remaining": operation.amount_remaining_to_settle,
            },
        )

    if amount_paid > operation.amount_remaining_to_settle:
        messages.error(
            request,
            _(
                "Payment cannot exceed remaining balance of %(balance)s."
                % {"balance": operation.amount_remaining_to_settle}
            ),
        )
        return render(
            request,
            "app_operation/purchase_wizard.html",
            {
                "project": project,
                "step": 3,
                "steps": STEPS,
                "current_step": STEPS[3],
                "operation": operation,
                "amount_remaining": operation.amount_remaining_to_settle,
            },
        )

    # Create payment transaction
    try:
        with transaction.atomic():
            operation.create_payment_transaction(
                amount=amount_paid,
                officer=request.user,
                date=operation.date,
                description=f"Instant payment for Purchase #{operation.pk}",
            )
    except Exception as e:
        messages.error(
            request,
            _("Error recording payment: %(error)s") % {"error": str(e)},
        )
        return render(
            request,
            "app_operation/purchase_wizard.html",
            {
                "project": project,
                "step": 3,
                "steps": STEPS,
                "current_step": STEPS[3],
                "operation": operation,
                "amount_remaining": operation.amount_remaining_to_settle,
            },
        )

    messages.success(request, _("Payment recorded."))
    return redirect(
        "purchase_wizard_step",
        pk=project.pk,
        operation_pk=operation.pk,
        step=4,
    )


# Step 4 handlers


def _get_step_4_context(request, project, operation):
    """Render Step 4: optional inventory movement."""
    movement = InventoryMovement.objects.filter(operation=operation).first()

    if movement:
        formset = InventoryMovementLineFormSet(instance=movement, operation=operation)
    else:
        formset = InventoryMovementLineFormSet(
            instance=InventoryMovement(), operation=operation
        )

    return {
        "operation": operation,
        "formset": formset,
        "movement": movement,
    }


def _handle_step_4_post(request, project, operation):
    """Handle Step 4 POST: optional inventory movement."""
    # Check if formset has any data (detect skip)
    formset = InventoryMovementLineFormSet(
        request.POST, instance=InventoryMovement(), operation=operation
    )

    # Count non-empty rows
    has_data = False
    for form in formset.forms:
        if form.cleaned_data and form.cleaned_data.get("invoice_item"):
            has_data = True
            break

    if not has_data:
        messages.info(request, _("Skipped goods receipt recording."))
        return redirect("operation_detail_view", pk=operation.pk)

    # Validate formset
    if not formset.is_valid():
        movement = InventoryMovement.objects.filter(operation=operation).first()
        return render(
            request,
            "app_operation/purchase_wizard.html",
            {
                "project": project,
                "step": 4,
                "steps": STEPS,
                "current_step": STEPS[4],
                "operation": operation,
                "formset": formset,
                "movement": movement,
            },
        )

    # Create inventory movement
    try:
        with transaction.atomic():
            movement = InventoryMovement(
                operation=operation,
                date=operation.date,
                officer=request.user,
                notes=request.POST.get("notes", ""),
            )
            movement.full_clean()
            movement.save()

            bound_formset = InventoryMovementLineFormSet(
                request.POST, instance=movement, operation=operation
            )
            bound_formset.is_valid()
            bound_formset.save()

    except Exception as e:
        messages.error(
            request,
            _("Error recording goods movement: %(error)s") % {"error": str(e)},
        )
        movement = InventoryMovement.objects.filter(operation=operation).first()
        return render(
            request,
            "app_operation/purchase_wizard.html",
            {
                "project": project,
                "step": 4,
                "steps": STEPS,
                "current_step": STEPS[4],
                "operation": operation,
                "formset": formset,
                "movement": movement,
            },
        )

    messages.success(request, _("Goods movement recorded."))
    return redirect("operation_detail_view", pk=operation.pk)
