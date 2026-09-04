"""Tests for the project setup wizard (create-only flow) - step 2: categories.

Step 2 only stores the selected financial categories into the session draft;
no category relations are created until the summary create.
"""

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType
from apps.app_entity.models.category import (
    FinancialCategoriesEntitiesRelations,
    FinancialCategory,
)
from apps.app_entity.views.project_setup_wizard import SESSION_KEY
from apps.app_inventory.tests.general import make_user


class ProjectSetupWizardStep2Test(TestCase):
    """Test step 2: financial categories are collected into the draft."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_wizard2", is_staff=True)
        self.client.login(username="officer_wizard2", password="testpass")

        self.category1 = FinancialCategory.objects.create(
            name="Revenue", aspect="revenue"
        )
        self.category2 = FinancialCategory.objects.create(
            name="Expense", aspect="expense"
        )

    def _start_draft(self):
        """Begin the wizard from step 1 (stored in the session)."""
        self.client.post(
            reverse("project_create"), {"name": "Wizard Project 2", "active": "on"}
        )

    def test_wizard_step_2_get_shows_categories(self):
        """GET of step 2 lists all categories as available."""
        self._start_draft()
        response = self.client.get(
            reverse("project_setup", kwargs={"step": 2})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["step"], 2)
        available = [
            category
            for group in response.context["available_by_aspect"].values()
            for category in group
        ]
        available_ids = {category.pk for category in available}
        self.assertIn(self.category1.pk, available_ids)
        self.assertIn(self.category2.pk, available_ids)

    def test_wizard_step_2_stores_selection_without_linking(self):
        """POST to step 2 stores the selection and creates no relations."""
        self._start_draft()
        response = self.client.post(
            reverse("project_setup", kwargs={"step": 2}),
            {
                "selected_categories": [
                    str(self.category1.pk),
                    str(self.category2.pk),
                ],
            },
        )

        self.assertRedirects(
            response, reverse("project_setup", kwargs={"step": 3})
        )
        self.assertEqual(FinancialCategoriesEntitiesRelations.objects.count(), 0)
        self.assertEqual(
            Entity.objects.filter(entity_type=EntityType.PROJECT).count(), 0
        )
        draft = self.client.session[SESSION_KEY]
        self.assertEqual(
            set(draft["categories"]), {self.category1.pk, self.category2.pk}
        )

    def test_wizard_step_2_requires_started_draft(self):
        """POST to step 2 without a draft bounces back to step 1."""
        response = self.client.post(
            reverse("project_setup", kwargs={"step": 2}),
            {"selected_categories": [str(self.category1.pk)]},
        )
        self.assertRedirects(response, reverse("project_create"))
