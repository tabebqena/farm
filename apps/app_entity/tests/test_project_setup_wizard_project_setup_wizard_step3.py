"""Tests for the project setup wizard (create-only flow) - step 3: templates.

Step 3 (staff only) stores the selected product templates into the session
draft; templates are not assigned to any entity until the summary create.
"""

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType
from apps.app_entity.views.project_setup_wizard import SESSION_KEY
from apps.app_inventory.models import ProductTemplate
from apps.app_inventory.tests.general import make_product_template, make_user


class ProjectSetupWizardStep3Test(TestCase):
    """Test step 3: product templates (staff only) are collected into the draft."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_wizard3", is_staff=True)
        self.client.login(username="officer_wizard3", password="testpass")
        self.template = make_product_template(name="Calves")

    def _start_draft(self):
        """Begin the wizard from step 1 (stored in the session)."""
        self.client.post(
            reverse("project_create"), {"name": "Wizard Project 3", "active": "on"}
        )

    def test_wizard_step_3_staff_stores_templates(self):
        """Staff POST to step 3 stores the templates and assigns nothing yet."""
        self._start_draft()
        response = self.client.post(
            reverse("project_setup", kwargs={"step": 3}),
            {"product_templates": [str(self.template.pk)]},
        )

        self.assertRedirects(
            response, reverse("project_setup", kwargs={"step": 4})
        )
        self.assertEqual(
            Entity.objects.filter(entity_type=EntityType.PROJECT).count(), 0
        )
        draft = self.client.session[SESSION_KEY]
        self.assertEqual(draft["templates"], [self.template.pk])

    def test_wizard_step_3_get_shows_templates(self):
        """Staff GET of step 3 lists templates with draft selections enabled."""
        self._start_draft()
        response = self.client.get(
            reverse("project_setup", kwargs={"step": 3})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["step"], 3)
        template_ids = list(
            response.context["templates"].values_list("id", flat=True)
        )
        self.assertIn(self.template.pk, template_ids)

    def test_wizard_step_3_non_staff_denied(self):
        """Non-staff POST to step 3 is rejected and nothing is stored."""
        make_user(username="plain_wizard3", is_staff=False)
        self.client.login(username="plain_wizard3", password="testpass")
        self._start_draft()

        response = self.client.post(
            reverse("project_setup", kwargs={"step": 3}),
            {"product_templates": [str(self.template.pk)]},
        )
        self.assertRedirects(
            response, reverse("project_setup", kwargs={"step": 3})
        )
        draft = self.client.session.get(SESSION_KEY, {})
        self.assertNotIn("templates", draft)

    def test_wizard_step_3_requires_started_draft(self):
        """POST to step 3 without a draft bounces back to step 1."""
        response = self.client.post(
            reverse("project_setup", kwargs={"step": 3}),
            {"product_templates": [str(self.template.pk)]},
        )
        self.assertRedirects(response, reverse("project_create"))
