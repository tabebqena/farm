"""Tests for the project setup wizard (create-only flow) - step 5: vendors.

Step 5 only stores the selected vendor entities into the session draft; no
stakeholder links are created until the summary create.
"""

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType, Stakeholder
from apps.app_entity.views.project_setup_wizard import SESSION_KEY
from apps.app_inventory.tests.general import make_user


class ProjectSetupWizardStep5Test(TestCase):
    """Test step 5: vendor stakeholders are collected into the draft."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_wizard5", is_staff=True)
        self.client.login(username="officer_wizard5", password="testpass")
        self.vendor = Entity.create(
            EntityType.PERSON, name="Vendor", is_vendor=True, active=True
        )

    def _start_draft(self):
        """Begin the wizard from step 1 (stored in the session)."""
        self.client.post(
            reverse("project_create"), {"name": "Wizard Project 5", "active": "on"}
        )

    def test_wizard_step_5_stores_vendors_without_linking(self):
        """POST to step 5 stores the vendors and creates no stakeholder rows."""
        self._start_draft()
        response = self.client.post(
            reverse("project_setup", kwargs={"step": 5}),
            {"selected_entities": [str(self.vendor.pk)]},
        )

        self.assertRedirects(
            response, reverse("project_setup", kwargs={"step": 6})
        )
        self.assertEqual(Stakeholder.objects.count(), 0)
        self.assertEqual(
            Entity.objects.filter(entity_type=EntityType.PROJECT).count(), 0
        )
        draft = self.client.session[SESSION_KEY]
        self.assertEqual(draft["vendors"], [self.vendor.pk])

    def test_wizard_step_5_get_reflects_selection(self):
        """GET of step 5 shows the eligible vendor pre-checked in the draft."""
        self._start_draft()
        self.client.post(
            reverse("project_setup", kwargs={"step": 5}),
            {"selected_entities": [str(self.vendor.pk)]},
        )
        response = self.client.get(
            reverse("project_setup", kwargs={"step": 5})
        )

        self.assertEqual(response.status_code, 200)
        eligible_ids = list(
            response.context["eligible_entities"].values_list("id", flat=True)
        )
        self.assertIn(self.vendor.pk, eligible_ids)
        self.assertIn(self.vendor.pk, response.context["existing_stakeholder_ids"])

    def test_wizard_step_5_requires_started_draft(self):
        """POST to step 5 without a draft bounces back to step 1."""
        response = self.client.post(
            reverse("project_setup", kwargs={"step": 5}),
            {"selected_entities": [str(self.vendor.pk)]},
        )
        self.assertRedirects(response, reverse("project_create"))
