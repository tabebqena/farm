"""Tests for the project setup wizard (create-only flow) - step 4: workers.

Step 4 only stores the selected worker entities into the session draft; no
stakeholder links are created until the summary create.
"""

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType, Stakeholder
from apps.app_entity.views.project_setup_wizard import SESSION_KEY
from apps.app_inventory.tests.general import make_user


class ProjectSetupWizardStep4Test(TestCase):
    """Test step 4: worker stakeholders are collected into the draft."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_wizard4", is_staff=True)
        self.client.login(username="officer_wizard4", password="testpass")
        self.worker = Entity.create(
            EntityType.PERSON, name="Worker", is_worker=True, active=True
        )

    def _start_draft(self):
        """Begin the wizard from step 1 (stored in the session)."""
        self.client.post(
            reverse("project_create"), {"name": "Wizard Project 4", "active": "on"}
        )

    def test_wizard_step_4_stores_workers_without_linking(self):
        """POST to step 4 stores the workers and creates no stakeholder rows."""
        self._start_draft()
        response = self.client.post(
            reverse("project_setup", kwargs={"step": 4}),
            {"selected_entities": [str(self.worker.pk)]},
        )

        self.assertRedirects(
            response, reverse("project_setup", kwargs={"step": 5})
        )
        self.assertEqual(Stakeholder.objects.count(), 0)
        self.assertEqual(
            Entity.objects.filter(entity_type=EntityType.PROJECT).count(), 0
        )
        draft = self.client.session[SESSION_KEY]
        self.assertEqual(draft["workers"], [self.worker.pk])

    def test_wizard_step_4_get_reflects_selection(self):
        """GET of step 4 shows the eligible worker pre-checked in the draft."""
        self._start_draft()
        self.client.post(
            reverse("project_setup", kwargs={"step": 4}),
            {"selected_entities": [str(self.worker.pk)]},
        )
        response = self.client.get(
            reverse("project_setup", kwargs={"step": 4})
        )

        self.assertEqual(response.status_code, 200)
        eligible_ids = list(
            response.context["eligible_entities"].values_list("id", flat=True)
        )
        self.assertIn(self.worker.pk, eligible_ids)
        self.assertIn(self.worker.pk, response.context["existing_stakeholder_ids"])

    def test_wizard_step_4_requires_started_draft(self):
        """POST to step 4 without a draft bounces back to step 1."""
        response = self.client.post(
            reverse("project_setup", kwargs={"step": 4}),
            {"selected_entities": [str(self.worker.pk)]},
        )
        self.assertRedirects(response, reverse("project_create"))
