"""Tests for the action-trace middleware and derived-row integration."""

from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from apps.app_audit import context as provenance
from apps.app_audit.middleware import ActionTraceMiddleware
from apps.app_audit.models import ActionTrace, SaveLog
from apps.app_audit.reasons import REASON_AUTO_PRODUCT
from apps.app_entity.models.category import FinancialCategory


@override_settings(FARM_TRACKING_ENABLED=True)
class MiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_mutating_request_creates_success_trace(self):
        def view(request):
            return HttpResponse("ok")

        middleware = ActionTraceMiddleware(view)
        request = self.factory.post("/entities/", {"name": "x"})
        response = middleware(request)
        self.assertEqual(response.status_code, 200)
        trace = ActionTrace.objects.get()
        self.assertEqual(trace.status, "success")
        self.assertEqual(trace.method, "POST")
        self.assertEqual(trace.payload["name"], ["x"])
        self.assertIsNotNone(trace.duration_ms)

    def test_exception_marks_failed_and_reraises(self):
        def view(request):
            raise ValueError("boom")

        middleware = ActionTraceMiddleware(view)
        request = self.factory.post("/entities/", {})
        with self.assertRaises(ValueError):
            middleware(request)
        trace = ActionTrace.objects.get()
        self.assertEqual(trace.status, "failed")
        self.assertIn("boom", trace.error)

    def test_get_request_is_not_traced(self):
        def view(request):
            return HttpResponse("ok")

        middleware = ActionTraceMiddleware(view)
        middleware(self.factory.get("/entities/"))
        self.assertEqual(ActionTrace.objects.count(), 0)

    def test_view_can_mark_failure_without_exception(self):
        def view(request):
            provenance.record_validation_error(
                "amount must be positive", field="amount", value="-1"
            )
            return HttpResponse("handled", status=400)

        middleware = ActionTraceMiddleware(view)
        middleware(self.factory.post("/entities/", {"amount": "-1"}))
        trace = ActionTrace.objects.get()
        self.assertEqual(trace.status, "failed")
        self.assertIn("amount", trace.error)

    def test_derived_saves_flow_through_middleware(self):
        def view(request):
            with provenance.derived("PRODUCT", REASON_AUTO_PRODUCT):
                category = FinancialCategory.objects.create(
                    name="Auto", aspect="EXPENSE"
                )
            provenance.set_root(category)
            return HttpResponse("ok")

        middleware = ActionTraceMiddleware(view)
        middleware(self.factory.post("/entities/", {}))
        trace = ActionTrace.objects.get()
        log = SaveLog.objects.get(model="financialcategory")
        self.assertTrue(log.is_derived)
        self.assertEqual(log.trace_id, trace.pk)
        self.assertEqual(trace.root_model, "financialcategory")

    @override_settings(FARM_TRACKING_ENABLED=False)
    def test_disabled_middleware_is_passthrough(self):
        def view(request):
            FinancialCategory.objects.create(name="Untracked", aspect="EXPENSE")
            return HttpResponse("ok")

        middleware = ActionTraceMiddleware(view)
        middleware(self.factory.post("/entities/", {}))
        self.assertEqual(ActionTrace.objects.count(), 0)
        self.assertEqual(SaveLog.objects.count(), 0)
