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


class ProjectSetupWizardStep2Test(TestCase):
    """Test step 2: Financial Categories."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_wizard2", is_staff=True)
        self.project = Entity.create(EntityType.PROJECT, name="Wizard Project 2")

        # Create test categories
        self.category1 = FinancialCategory.objects.create(
            name="Revenue", aspect="revenue"
        )
        self.category2 = FinancialCategory.objects.create(
            name="Expense", aspect="expense"
        )

    def test_wizard_step_2_get_shows_categories(self):
        """Test GET request to step 2 shows available categories."""
        self.client.login(username="officer_wizard2", password="testpass")
        response = self.client.get(
            reverse("project_setup_step", kwargs={"entity_pk": self.project.pk, "step": 2})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["step"], 2)

    def test_wizard_step_2_links_categories(self):
        """Test POST to step 2 links selected categories."""
        self.client.login(username="officer_wizard2", password="testpass")
        response = self.client.post(
            reverse("project_setup_step", kwargs={"entity_pk": self.project.pk, "step": 2}),
            {
                "selected_categories": [str(self.category1.pk), str(self.category2.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)
        relations = FinancialCategoriesEntitiesRelations.objects.filter(
            entity=self.project
        )
        self.assertEqual(relations.count(), 2)
        self.assertTrue(relations.filter(category=self.category1).exists())
        self.assertTrue(relations.filter(category=self.category2).exists())

    def test_wizard_step_2_activates_deactivates(self):
        """Test step 2 can activate/deactivate categories."""
        # Pre-link both
        FinancialCategoriesEntitiesRelations.objects.create(
            entity=self.project, category=self.category1, is_active=True
        )
        FinancialCategoriesEntitiesRelations.objects.create(
            entity=self.project, category=self.category2, is_active=True
        )

        self.client.login(username="officer_wizard2", password="testpass")
        # Now select only category1
        response = self.client.post(
            reverse("project_setup_step", kwargs={"entity_pk": self.project.pk, "step": 2}),
            {
                "selected_categories": [str(self.category1.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)
        rel1 = FinancialCategoriesEntitiesRelations.objects.get(
            entity=self.project, category=self.category1
        )
        rel2 = FinancialCategoriesEntitiesRelations.objects.get(
            entity=self.project, category=self.category2
        )
        self.assertTrue(rel1.is_active)
        self.assertFalse(rel2.is_active)
