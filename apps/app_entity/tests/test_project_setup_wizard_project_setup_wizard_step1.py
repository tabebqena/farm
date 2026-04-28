"""Tests for project setup wizard (all 6 steps)."""

from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import (
    Entity,
    EntityType,
    Stakeholder,
    StakeholderRole,
)
from apps.app_entity.models.category import (
    FinancialCategory,
    FinancialCategoriesEntitiesRelations,
)
from apps.app_inventory.models import ProductTemplate
from apps.app_inventory.tests.general import make_user


class ProjectSetupWizardStep1Test(TestCase):
    """Test step 1: Project Info creation."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_wizard", is_staff=True)

    def test_wizard_step_1_get_renders_form(self):
        """Test GET request to step 1 shows form."""
        self.client.login(username="officer_wizard", password="testpass")
        response = self.client.get(reverse("project_create"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["step"], 1)

    def test_wizard_step_1_creates_project(self):
        """Test POST to step 1 creates project entity."""
        self.client.login(username="officer_wizard", password="testpass")
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

        # Should redirect to step 2
        self.assertEqual(response.status_code, 302)
        entity = Entity.objects.get(name="Wizard Project")
        self.assertEqual(entity.entity_type, EntityType.PROJECT)
        self.assertTrue(entity.is_internal)
        self.assertTrue(entity.active)


    def test_wizard_step_1_edit_existing(self):
        """Test step 1 can edit existing project."""
        project = Entity.create(EntityType.PROJECT, name="To Edit")
        self.client.login(username="officer_wizard", password="testpass")
        response = self.client.post(
            reverse("project_setup_step", kwargs={"entity_pk": project.pk, "step": 1}),
            {
                "name": "Edited Project",
                "description": "Updated via wizard",
                "is_internal": "",
                "is_vendor": "on",
                "is_client": "",
                "active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        project.refresh_from_db()
        self.assertEqual(project.name, "Edited Project")
        self.assertTrue(project.is_vendor)
