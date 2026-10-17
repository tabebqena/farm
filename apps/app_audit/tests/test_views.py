"""Tests for the audit inspection views."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.app_audit.models import ActionTrace, SaveLog

User = get_user_model()


class AuditViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="officer", password="pw")
        self.client.force_login(self.user)
        self.trace = ActionTrace.objects.create(
            actor=self.user,
            method="POST",
            path="/entities/operations/create/",
            action="operation_create_view",
            payload={"amount": ["100"]},
        )
        self.save_log = SaveLog.objects.create(
            trace=self.trace,
            actor=self.user,
            app_label="app_operation",
            model="operation",
            object_id="7",
            object_repr="Sale #7",
            kind="create",
            new_shape={"amount": "100", "source": {"model": "app_entity.entity", "pk": 1}},
            is_derived=True,
            role="ISSUANCE_TXN",
            reason_code="AUTO_ISSUANCE",
            reason_text="Auto issuance",
        )

    def test_activity_list(self):
        response = self.client.get(reverse("audit_activity"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "operation_create_view")

    def test_activity_filter_by_status(self):
        response = self.client.get(reverse("audit_activity"), {"status": "failed"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "operation_create_view")

    def test_trace_detail_all_levels(self):
        response = self.client.get(reverse("audit_trace_detail", args=[self.trace.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "What you submitted")
        self.assertContains(response, "100")
        self.assertContains(response, "AUTO_ISSUANCE")

    def test_record_history(self):
        response = self.client.get(
            reverse("audit_record_history", args=["app_operation", "operation", "7"])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Auto issuance")

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(reverse("audit_activity"))
        self.assertNotEqual(response.status_code, 200)
