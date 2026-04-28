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


class ProjectSetupWizardStep5Test(TestCase):
    """Test step 5: Vendor Stakeholders."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_wizard5", is_staff=True)
        self.project = Entity.create(EntityType.PROJECT, name="Wizard Project 5")

        # Create eligible vendors
        self.vendor1 = Entity.create(
            EntityType.PERSON, name="Vendor 1", is_vendor=True, active=True
        )
        self.vendor2 = Entity.create(
            EntityType.PERSON, name="Vendor 2", is_vendor=True, active=True
        )

    def test_wizard_step_5_get_shows_eligible_vendors(self):
        """Test GET request to step 5 shows eligible vendors."""
        self.client.login(username="officer_wizard5", password="testpass")
        response = self.client.get(
            reverse("project_setup_step", kwargs={"entity_pk": self.project.pk, "step": 5})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["step"], 5)
        self.assertIn(self.vendor1, response.context["eligible_entities"])

    def test_wizard_step_5_adds_vendors(self):
        """Test POST to step 5 creates vendor stakeholders."""
        self.client.login(username="officer_wizard5", password="testpass")
        response = self.client.post(
            reverse("project_setup_step", kwargs={"entity_pk": self.project.pk, "step": 5}),
            {
                "selected_entities": [str(self.vendor1.pk), str(self.vendor2.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)
        stakeholders = Stakeholder.objects.filter(parent=self.project, role="vendor")
        self.assertEqual(stakeholders.count(), 2)
