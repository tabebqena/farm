"""Shared session-wizard scaffolding for the Purchase and Sale wizards.

Both wizards are multi-step, session-only flows that build up an invoice in the
session and submit it through ``create_from_session()`` on the operation proxy.
The steps, session handling, invoice scaffolding and submission are
direction-agnostic; this module holds that shared scaffolding, parameterized by
a :class:`Wizard` config. Each wizard module keeps only its direction-specific
bits: the project guard, the item selector (template vs product) and the submit
factory call.
"""
import logging
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from apps.app_entity.models import Entity

logger = logging.getLogger(__name__)


def sum_item_totals(items):
    """Sum of (quantity × unit_price) for a list of session item dicts."""
    return sum(
        Decimal(item["quantity"]) * Decimal(item["unit_price"]) for item in items
    )


class Wizard:
    """Direction-specific knobs + shared behavior for a session wizard."""

    def __init__(
        self,
        *,
        prefix,
        steps,
        counterpart_field,
        step1_form_class,
        step2_form_class,
        step3_form_class,
        step1_url,
        step_new_url,
        invoice_url,
        cancel_url,
        submit_url,
        template_name,
        invoice_template_name,
        recorded_message,
        operation_list_url_name="operation_list_view",
        detail_url_name="operation_detail_view",
    ):
        self.prefix = prefix
        self.steps = steps
        self.counterpart_field = counterpart_field
        self.step1_form_class = step1_form_class
        self.step2_form_class = step2_form_class
        self.step3_form_class = step3_form_class
        self.step1_url = step1_url
        self.step_new_url = step_new_url
        self.invoice_url = invoice_url
        self.cancel_url = cancel_url
        self.submit_url = submit_url
        self.template_name = template_name
        self.invoice_template_name = invoice_template_name
        self.recorded_message = recorded_message
        self.operation_list_url_name = operation_list_url_name
        self.detail_url_name = detail_url_name

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    def _key(self, pk):
        return f"{self.prefix}_{pk}"

    def get_session(self, request, pk):
        return request.session.get(self._key(pk), {})

    def save_session(self, request, pk, data):
        request.session[self._key(pk)] = data
        request.session.modified = True

    def clear_session(self, request, pk):
        key = self._key(pk)
        request.session.pop(key, None)
        request.session.modified = True

    # ------------------------------------------------------------------
    # Generic views
    # ------------------------------------------------------------------

    def cancel(self, request, pk):
        self.clear_session(request, pk)
        return redirect(self.operation_list_url_name, person_pk=pk)

    def handle_wizard(self, request, pk, step, project):
        """Step router + GET renderer (project already loaded by the caller)."""
        if step not in self.steps:
            messages.error(request, _("Invalid wizard step."))
            return redirect(self.operation_list_url_name, person_pk=pk)

        session = self.get_session(request, pk)

        # Steps 2-3 require step 1 session data.
        if step >= 2 and "date" not in session:
            messages.error(
                request, _("Session expired. Please start from the beginning.")
            )
            return redirect(self.step1_url, pk=pk)

        if request.method == "POST":
            if step == 1:
                return self._handle_step_1_post(request, project, session)
            if step == 2:
                return self._handle_step_2_post(request, project, session)
            if step == 3:
                return self._handle_step_3_post(request, project, session)

        next_param = request.GET.get("next", "")
        context = {
            "project": project,
            "step": step,
            "steps": self.steps,
            "current_step": self.steps[step],
            "next_param": next_param,
        }

        if step == 1:
            initial = {
                "date": session.get("date", date.today().isoformat()),
                self.counterpart_field: session.get(f"{self.counterpart_field}_id"),
                "description": session.get("description", ""),
            }
            context["form"] = self.step1_form_class(initial=initial, project=project)
        elif step == 2:
            initial = {"total_amount": session.get("total_amount")}
            context["form"] = self.step2_form_class(initial=initial)
            context["step1_data"] = self.resolve_step1_display(session)
        elif step == 3:
            initial = {"amount_paid": session.get("amount_paid") or ""}
            context["form"] = self.step3_form_class(initial=initial)
            context["total_amount"] = session.get("total_amount")

        return render(request, self.template_name, context)

    def render_invoice(self, request, pk, project, augment_item):
        """Render the invoice hub; ``augment_item(item)`` adds item display fields."""
        session = self.get_session(request, pk)
        if "total_amount" not in session:
            messages.error(
                request, _("Session expired. Please start from the beginning.")
            )
            return redirect(self.step1_url, pk=pk)

        total_amount = Decimal(session["total_amount"])
        raw_items = session.get("items", [])

        items = []
        for item in raw_items:
            qty = Decimal(item["quantity"])
            price = Decimal(item["unit_price"])
            items.append({**item, **augment_item(item), "total_price": qty * price})

        items_total = sum_item_totals(raw_items)
        difference = total_amount - items_total
        submit_enabled = abs(difference) <= Decimal("0.01")
        counterpart = self.resolve_step1_display(session).get(self.counterpart_field)

        return render(
            request,
            self.invoice_template_name,
            {
                "project": project,
                "session_data": session,
                "items": items,
                "items_total": items_total,
                "difference": difference,
                "submit_enabled": submit_enabled,
                self.counterpart_field: counterpart,
            },
        )

    def delete_item(self, request, pk, idx):
        if request.method != "POST":
            return redirect(self.invoice_url, pk=pk)

        session = self.get_session(request, pk)
        items = session.get("items", [])
        if 0 <= idx < len(items):
            items = [item for i, item in enumerate(items) if i != idx]
            for i, item in enumerate(items):
                item["idx"] = i
            session["items"] = items
            self.save_session(request, pk, session)
        return redirect(self.invoice_url, pk=pk)

    def submit(self, request, pk, project, create):
        """Submit the session invoice via ``create(request, project, session)``."""
        if request.method != "POST":
            return redirect(self.invoice_url, pk=pk)

        session = self.get_session(request, pk)
        if "total_amount" not in session:
            messages.error(
                request, _("Session expired. Please start from the beginning.")
            )
            return redirect(self.step1_url, pk=pk)

        items = session.get("items", [])
        if not items:
            messages.error(request, _("Add at least one item before submitting."))
            return redirect(self.invoice_url, pk=pk)

        try:
            op = create(request, project, session)
        except Exception as e:
            logger.exception("Error during wizard submit")
            messages.error(request, _("Error: %(e)s") % {"e": str(e)})
            return redirect(self.invoice_url, pk=pk)

        self.clear_session(request, pk)
        messages.success(request, self.recorded_message)
        return redirect(self.detail_url_name, pk=op.pk)

    # ------------------------------------------------------------------
    # Step 1-3 POST handlers
    # ------------------------------------------------------------------

    def _handle_step_1_post(self, request, project, session):
        form = self.step1_form_class(request.POST, project=project)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {
                    "project": project,
                    "step": 1,
                    "steps": self.steps,
                    "current_step": self.steps[1],
                    "form": form,
                },
            )
        session.update(
            {
                "date": form.cleaned_data["date"].isoformat(),
                f"{self.counterpart_field}_id": form.cleaned_data[
                    self.counterpart_field
                ].pk,
                "description": form.cleaned_data["description"],
                "items": session.get("items", []),
            }
        )
        self.save_session(request, project.pk, session)
        return redirect(self.step_new_url, pk=project.pk, step=2)

    def _handle_step_2_post(self, request, project, session):
        next_param = request.POST.get("next", "")
        form = self.step2_form_class(request.POST)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {
                    "project": project,
                    "step": 2,
                    "steps": self.steps,
                    "current_step": self.steps[2],
                    "form": form,
                    "step1_data": self.resolve_step1_display(session),
                    "next_param": next_param,
                },
            )
        session["total_amount"] = str(form.cleaned_data["total_amount"])
        self.save_session(request, project.pk, session)
        if next_param == "invoice":
            return redirect(self.invoice_url, pk=project.pk)
        return redirect(self.step_new_url, pk=project.pk, step=3)

    def _handle_step_3_post(self, request, project, session):
        next_param = request.POST.get("next", "")
        form = self.step3_form_class(request.POST)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {
                    "project": project,
                    "step": 3,
                    "steps": self.steps,
                    "current_step": self.steps[3],
                    "form": form,
                    "total_amount": session.get("total_amount"),
                    "next_param": next_param,
                },
            )
        paid = form.cleaned_data["amount_paid"]
        total = Decimal(session["total_amount"])
        if paid > total:
            form.add_error("amount_paid", _("Payment cannot exceed the declared total."))
            return render(
                request,
                self.template_name,
                {
                    "project": project,
                    "step": 3,
                    "steps": self.steps,
                    "current_step": self.steps[3],
                    "form": form,
                    "total_amount": session.get("total_amount"),
                    "next_param": next_param,
                },
            )
        session["amount_paid"] = str(paid)
        self.save_session(request, project.pk, session)
        return redirect(self.invoice_url, pk=project.pk)

    # ------------------------------------------------------------------
    # Step 1 display helper
    # ------------------------------------------------------------------

    def resolve_step1_display(self, session):
        """Return step 1 values suitable for read-only display."""
        counterpart = None
        counterpart_id = session.get(f"{self.counterpart_field}_id")
        if counterpart_id:
            try:
                counterpart = Entity.objects.get(pk=counterpart_id)
            except Entity.DoesNotExist:
                pass
        return {
            "date": session.get("date", ""),
            self.counterpart_field: counterpart,
            "description": session.get("description", ""),
        }
