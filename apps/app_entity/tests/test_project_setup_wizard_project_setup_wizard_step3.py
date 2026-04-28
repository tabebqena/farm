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


class ProjectSetupWizardStep3Test(TestCase):
    """Test step 3: Product Templates."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_wizard3", is_staff=True)
        self.project = Entity.create(EntityType.PROJECT, name="Wizard Project 3")

        # Create test product templates
        self.template1 = ProductTemplate.objects.create(
            name="Template 1",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="livestock",
            tracking_mode=ProductTemplate.TrackingMode.BATCH,
            default_unit="Head",
        )
        self.template2 = ProductTemplate.objects.create(
            name="Template 2",
            nature=ProductTemplate.Nature.FEED,
            sub_category="feed",
            tracking_mode=ProductTemplate.TrackingMode.COMMODITY,
            default_unit="kg",
        )

    def test_wizard_step_3_get_shows_templates(self):
        """Test GET request to step 3 shows available templates."""
        self.client.login(username="officer_wizard3", password="testpass")
        response = self.client.get(
            reverse("project_setup_step", kwargs={"entity_pk": self.project.pk, "step": 3})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["step"], 3)

    def test_wizard_step_3_assigns_templates(self):
        """Test POST to step 3 assigns product templates."""
        self.client.login(username="officer_wizard3", password="testpass")
        response = self.client.post(
            reverse("project_setup_step", kwargs={"entity_pk": self.project.pk, "step": 3}),
            {
                "product_templates": [str(self.template1.pk), str(self.template2.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.project.product_templates.count(), 2)
        self.assertTrue(
            self.project.product_templates.filter(pk=self.template1.pk).exists()
        )
        self.assertTrue(
            self.project.product_templates.filter(pk=self.template2.pk).exists()
        )

    def test_wizard_step_3_no_templates_allowed(self):
        """Test step 3 allows no templates selected."""
        self.client.login(username="officer_wizard3", password="testpass")
        response = self.client.post(
            reverse("project_setup_step", kwargs={"entity_pk": self.project.pk, "step": 3}),
            {"product_templates": []},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.project.product_templates.count(), 0)
