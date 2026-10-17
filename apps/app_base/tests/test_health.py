"""Tests for the unauthenticated liveness endpoint."""

from django.test import SimpleTestCase
from django.urls import reverse


class HealthCheckTests(SimpleTestCase):
    """The health probe must answer without authentication or a database."""

    def test_healthz_returns_ok_without_auth(self):
        response = self.client.get(reverse("healthz"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")
