"""Tests for the project setup wizard (create-only flow) - step 1.

Step 1 only collects the project identity into the session draft; the project
Entity is created later, atomically, from the summary step.
"""

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType
from apps.app_entity.views.project_setup_wizard import SESSION_KEY
from apps.app_inventory.tests.general import make_user


class ProjectSetupWizardStep1Test(TestCase):
    """Test step 1: project info is drafted, never created."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_wizard", is_staff=True)
        self.client.login(username="officer_wizard", password="testpass")

    def test_wizard_step_1_get_renders_form(self):
        """GET of step 1 renders the project-info form."""
        response = self.client.get(reverse("project_create"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["step"], 1)
        self.assertEqual(response.context["total_steps"], 7)

    def test_wizard_step_1_defaults_client_and_vendor(self):
        """A fresh wizard defaults is_client and is_vendor to True (checked)."""
        response = self.client.get(reverse("project_create"))

        self.assertEqual(response.status_code, 200)
        draft_info = response.context["draft_info"]
        self.assertTrue(draft_info["is_vendor"])
        self.assertTrue(draft_info["is_client"])
        # Both checkboxes must be rendered pre-checked for a fresh draft.
        content = response.content.decode()
        self.assertIn('name="is_vendor"', content)
        self.assertIn('name="is_client"', content)
        self.assertIn("checked", content)

    def test_wizard_step_1_stores_draft_without_creating_project(self):
        """POST to step 1 stores the draft and does NOT create a project."""
        response = self.client.post(
            reverse("project_create"),
            {
                "name": "Wizard Project",
                "description": "Created via wizard",
                "is_internal": "on",
                "is_vendor": "",
                "is_client": "",
                "active": "on",
            },
        )

        self.assertRedirects(
            response, reverse("project_setup", kwargs={"step": 2})
        )
        # The project must not be created at step 1.
        self.assertEqual(
            Entity.objects.filter(entity_type=EntityType.PROJECT).count(), 0
        )
        draft = self.client.session[SESSION_KEY]
        self.assertEqual(draft["info"]["name"], "Wizard Project")
        self.assertEqual(draft["info"]["description"], "Created via wizard")
        self.assertTrue(draft["info"]["is_internal"])
        self.assertFalse(draft["info"]["is_vendor"])
        self.assertTrue(draft["info"]["active"])

    def test_wizard_step_1_requires_name(self):
        """POST to step 1 with an empty name stays on step 1 with no draft."""
        response = self.client.post(
            reverse("project_create"),
            {"name": "", "description": "no name"},
        )

        self.assertRedirects(response, reverse("project_create"))
        self.assertEqual(
            Entity.objects.filter(entity_type=EntityType.PROJECT).count(), 0
        )
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_wizard_later_step_requires_started_draft(self):
        """Accessing a later step without a draft bounces back to step 1."""
        response = self.client.get(
            reverse("project_setup", kwargs={"step": 3})
        )
        self.assertRedirects(response, reverse("project_create"))

    def test_wizard_cancel_clears_draft(self):
        """Cancelling the wizard clears the draft and returns to the list."""
        self.client.post(reverse("project_create"), {"name": "Cancel Me"})
        self.assertIn(SESSION_KEY, self.client.session)

        response = self.client.get(reverse("project_setup_cancel"))
        self.assertRedirects(response, reverse("entity_list"))
        self.assertNotIn(SESSION_KEY, self.client.session)
