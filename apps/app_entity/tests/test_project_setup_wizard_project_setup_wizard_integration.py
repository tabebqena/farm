"""Integration tests for the project setup wizard (create-only flow).

The wizard collects steps 1-6 into a session draft and only creates the project
atomically from the summary step (step 7). A per-stage failure rolls the whole
creation back and redirects the user to the step whose data failed.
"""

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType, Stakeholder
from apps.app_entity.models.category import (
    FinancialCategoriesEntitiesRelations,
    FinancialCategory,
)
from apps.app_entity.views.project_setup_wizard import SESSION_KEY
from apps.app_inventory.tests.general import make_product_template, make_user


class ProjectSetupWizardIntegrationTest(TestCase):
    """Test full create-only wizard flow from start to finish."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_full", is_staff=True)
        self.client.login(username="officer_full", password="testpass")

        # Create resources for the later steps
        self.category = FinancialCategory.objects.create(
            name="Revenue", aspect="revenue"
        )
        self.template = make_product_template(name="Calves")
        self.worker = Entity.create(
            EntityType.PERSON, name="Worker", is_worker=True, active=True
        )
        self.vendor = Entity.create(
            EntityType.PERSON, name="Vendor", is_vendor=True, active=True
        )
        self.shareholder = Entity.create(
            EntityType.PERSON,
            name="Shareholder",
            is_shareholder=True,
            active=True,
        )

    def test_complete_wizard_flow_creates_project_on_summary(self):
        """Walk all steps, then Create on the summary builds everything."""
        # Step 1: collect project info (no creation)
        response = self.client.post(
            reverse("project_create"),
            {
                "name": "Complete Project",
                "description": "Full wizard test",
                "is_internal": "on",
                "is_vendor": "",
                "is_client": "",
                "active": "on",
            },
        )
        self.assertRedirects(
            response, reverse("project_setup", kwargs={"step": 2})
        )

        # Step 2: link categories (draft only)
        response = self.client.post(
            reverse("project_setup", kwargs={"step": 2}),
            {"selected_categories": [str(self.category.pk)]},
        )
        self.assertRedirects(
            response, reverse("project_setup", kwargs={"step": 3})
        )

        # Step 3: assign templates (draft only)
        response = self.client.post(
            reverse("project_setup", kwargs={"step": 3}),
            {"product_templates": [str(self.template.pk)]},
        )
        self.assertRedirects(
            response, reverse("project_setup", kwargs={"step": 4})
        )

        # Step 4: workers (draft only)
        response = self.client.post(
            reverse("project_setup", kwargs={"step": 4}),
            {"selected_entities": [str(self.worker.pk)]},
        )
        self.assertRedirects(
            response, reverse("project_setup", kwargs={"step": 5})
        )

        # Step 5: vendors (draft only)
        response = self.client.post(
            reverse("project_setup", kwargs={"step": 5}),
            {"selected_entities": [str(self.vendor.pk)]},
        )
        self.assertRedirects(
            response, reverse("project_setup", kwargs={"step": 6})
        )

        # Step 6: shareholders (draft only)
        response = self.client.post(
            reverse("project_setup", kwargs={"step": 6}),
            {"selected_entities": [str(self.shareholder.pk)]},
        )
        self.assertRedirects(
            response, reverse("project_setup", kwargs={"step": 7})
        )

        # Nothing may exist yet.
        self.assertEqual(
            Entity.objects.filter(entity_type=EntityType.PROJECT).count(), 0
        )
        self.assertEqual(FinancialCategoriesEntitiesRelations.objects.count(), 0)
        self.assertEqual(Stakeholder.objects.count(), 0)

        # Summary GET shows the collected data.
        response = self.client.get(
            reverse("project_setup", kwargs={"step": 7})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["step"], 7)
        self.assertEqual(
            response.context["summary_counts"],
            {
                "categories": 1,
                "templates": 1,
                "workers": 1,
                "vendors": 1,
                "shareholders": 1,
            },
        )

        # Summary POST: Create Project.
        response = self.client.post(
            reverse("project_setup", kwargs={"step": 7}), {}, follow=True
        )
        self.assertEqual(response.status_code, 200)

        project = Entity.objects.get(name="Complete Project")
        self.assertEqual(project.entity_type, EntityType.PROJECT)
        self.assertTrue(project.is_internal)
        self.assertTrue(project.active)
        self.assertEqual(project.product_templates.count(), 1)
        self.assertEqual(
            FinancialCategoriesEntitiesRelations.objects.filter(
                entity=project, category=self.category, is_active=True
            ).count(),
            1,
        )
        self.assertEqual(
            Stakeholder.objects.filter(parent=project, role="worker").count(), 1
        )
        self.assertEqual(
            Stakeholder.objects.filter(parent=project, role="vendor").count(), 1
        )
        self.assertEqual(
            Stakeholder.objects.filter(parent=project, role="shareholder").count(),
            1,
        )
        # The draft is cleared after a successful create.
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_category_failure_rolls_back_and_redirects_to_step_2(self):
        """A missing selected category prevents creation and returns to step 2."""
        # Start the wizard
        self.client.post(
            reverse("project_create"),
            {"name": "Broken Categories Project", "active": "on"},
        )
        # Store a category id that does not exist
        response = self.client.post(
            reverse("project_setup", kwargs={"step": 2}),
            {"selected_categories": ["999999"]},
        )
        self.assertRedirects(
            response, reverse("project_setup", kwargs={"step": 3})
        )

        response = self.client.post(
            reverse("project_setup", kwargs={"step": 7}), {}
        )
        self.assertRedirects(
            response, reverse("project_setup", kwargs={"step": 2})
        )
        # No project or relation rows survive the rollback.
        self.assertEqual(
            Entity.objects.filter(entity_type=EntityType.PROJECT).count(), 0
        )
        self.assertEqual(FinancialCategoriesEntitiesRelations.objects.count(), 0)
        # The draft is preserved so the user can fix step 2.
        self.assertEqual(
            self.client.session[SESSION_KEY]["categories"], [999999]
        )

    def test_worker_failure_redirects_to_step_4(self):
        """An ineligible worker selection prevents creation and returns to step 4."""
        # Start the wizard
        self.client.post(
            reverse("project_create"),
            {"name": "Broken Workers Project", "active": "on"},
        )
        # Select a person who is not a worker
        response = self.client.post(
            reverse("project_setup", kwargs={"step": 4}),
            {"selected_entities": [str(self.vendor.pk)]},
        )
        self.assertRedirects(
            response, reverse("project_setup", kwargs={"step": 5})
        )

        response = self.client.post(
            reverse("project_setup", kwargs={"step": 7}), {}
        )
        self.assertRedirects(
            response, reverse("project_setup", kwargs={"step": 4})
        )
        self.assertEqual(
            Entity.objects.filter(entity_type=EntityType.PROJECT).count(), 0
        )
        self.assertEqual(Stakeholder.objects.count(), 0)
