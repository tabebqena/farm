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


class ProjectSetupWizardStep6Test(TestCase):
    """Test step 6: Shareholder Stakeholders (final step)."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_wizard6", is_staff=True)
        self.project = Entity.create(EntityType.PROJECT, name="Wizard Project 6")

        # Create eligible shareholders
        self.shareholder1 = Entity.create(
            EntityType.PERSON, name="Shareholder 1", is_shareholder=True, active=True
        )
        self.shareholder2 = Entity.create(
            EntityType.PERSON, name="Shareholder 2", is_shareholder=True, active=True
        )

    def test_wizard_step_6_get_shows_eligible_shareholders(self):
        """Test GET request to step 6 shows eligible shareholders."""
        self.client.login(username="officer_wizard6", password="testpass")
        response = self.client.get(
            reverse("project_setup_step", kwargs={"entity_pk": self.project.pk, "step": 6})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["step"], 6)
        self.assertIn(self.shareholder1, response.context["eligible_entities"])

    def test_wizard_step_6_adds_shareholders(self):
        """Test POST to step 6 creates shareholder stakeholders."""
        self.client.login(username="officer_wizard6", password="testpass")
        response = self.client.post(
            reverse("project_setup_step", kwargs={"entity_pk": self.project.pk, "step": 6}),
            {
                "selected_entities": [str(self.shareholder1.pk), str(self.shareholder2.pk)],
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        stakeholders = Stakeholder.objects.filter(parent=self.project, role="shareholder")
        self.assertEqual(stakeholders.count(), 2)
        # Should redirect to entity detail
        self.assertContains(response, self.project.name)

    def test_wizard_step_6_redirects_to_detail(self):
        """Test step 6 redirects to entity detail on completion."""
        self.client.login(username="officer_wizard6", password="testpass")
        response = self.client.post(
            reverse("project_setup_step", kwargs={"entity_pk": self.project.pk, "step": 6}),
            {"selected_entities": []},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        # Verify redirected to entity detail
        self.assertContains(response, self.project.name)
