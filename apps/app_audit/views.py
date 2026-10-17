"""Views for inspecting the action provenance trail.

- :class:`ActivityListView` — the filterable list of traced actions.
- :class:`TraceDetailView` — one action shown at all three levels (input,
  auto-created rows with reasons, every save).
- :class:`RecordHistoryView` — the "why does this row exist?" view for a single
  record, listing every save that touched it and the action behind each.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView, ListView

from .models import ActionTrace, SaveLog


class ActivityListView(LoginRequiredMixin, ListView):
    """List traced actions, newest first, with optional filters."""

    model = ActionTrace
    template_name = "app_audit/activity.html"
    context_object_name = "traces"
    paginate_by = 50

    def get_queryset(self):
        qs = ActionTrace.objects.select_related("actor")
        params = self.request.GET
        actor = params.get("actor")
        if actor:
            qs = qs.filter(actor__username=actor)
        status = params.get("status")
        if status:
            qs = qs.filter(status=status)
        q = params.get("q")
        if q:
            qs = qs.filter(action__icontains=q) | qs.filter(path__icontains=q)
        date_from = params.get("date_from")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        date_to = params.get("date_to")
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filters"] = self.request.GET
        return context


class TraceDetailView(LoginRequiredMixin, DetailView):
    """One action: input, auto-created rows, and every save."""

    model = ActionTrace
    template_name = "app_audit/trace_detail.html"
    context_object_name = "trace"

    def get_queryset(self):
        return ActionTrace.objects.select_related("actor")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        saves = list(self.object.saves.select_related("actor").order_by("pk"))
        context["all_saves"] = saves
        context["derived_saves"] = [save for save in saves if save.is_derived]
        context["payload_items"] = sorted((self.object.payload or {}).items())
        return context


class RecordHistoryView(LoginRequiredMixin, ListView):
    """Every recorded save for one record, newest last."""

    template_name = "app_audit/record_history.html"
    context_object_name = "saves"
    paginate_by = 100

    def get_queryset(self):
        self.app_label = self.kwargs["app_label"]
        self.model = self.kwargs["model"]
        self.object_id = self.kwargs["object_id"]
        return SaveLog.objects.filter(
            app_label=self.app_label,
            model=self.model,
            object_id=self.object_id,
        ).select_related("trace", "trace__actor", "actor")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["app_label"] = self.app_label
        context["model"] = self.model
        context["object_id"] = self.object_id
        first = self.get_queryset().first()
        context["object_repr"] = first.object_repr if first else ""
        return context
