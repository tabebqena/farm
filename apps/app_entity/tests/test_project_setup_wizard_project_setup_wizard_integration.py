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


class ProjectSetupWizardIntegrationTest(TestCase):
    """Test full wizard flow from start to finish."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_full", is_staff=True)

        # Create resources for later steps
        self.category = FinancialCategory.objects.create(
            name="Revenue", aspect="revenue"
        )
        self.template = ProductTemplate.objects.create(
            name="Template",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="livestock",
            tracking_mode=ProductTemplate.TrackingMode.BATCH,
            default_unit="Head",
        )
        self.worker = Entity.create(
            EntityType.PERSON, name="Worker", is_worker=True, active=True
        )
        self.vendor = Entity.create(
            EntityType.PERSON, name="Vendor", is_vendor=True, active=True
        )
        self.shareholder = Entity.create(
            EntityType.PERSON, name="Shareholder", is_shareholder=True, active=True
        )

    def test_complete_wizard_flow(self):
        """Test completing all 6 wizard steps."""
        self.client.login(username="officer_full", password="testpass")

        # Step 1: Create project
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
        self.assertEqual(response.status_code, 302)
        project = Entity.objects.get(name="Complete Project")

        # Step 2: Link categories
        response = self.client.post(
            reverse(
                "project_setup_step", kwargs={"entity_pk": project.pk, "step": 2}
            ),
            {"selected_categories": [str(self.category.pk)]},
        )
        self.assertEqual(response.status_code, 302)

        # Step 3: Assign templates
        response = self.client.post(
            reverse(
                "project_setup_step", kwargs={"entity_pk": project.pk, "step": 3}
            ),
            {"product_templates": [str(self.template.pk)]},
        )
        self.assertEqual(response.status_code, 302)

        # Step 4: Add workers
        response = self.client.post(
            reverse(
                "project_setup_step", kwargs={"entity_pk": project.pk, "step": 4}
            ),
            {"selected_entities": [str(self.worker.pk)]},
        )
        self.assertEqual(response.status_code, 302)

        # Step 5: Add vendors
        response = self.client.post(
            reverse(
                "project_setup_step", kwargs={"entity_pk": project.pk, "step": 5}
            ),
            {"selected_entities": [str(self.vendor.pk)]},
        )
        self.assertEqual(response.status_code, 302)

        # Step 6: Add shareholders (final step)
        response = self.client.post(
            reverse(
                "project_setup_step", kwargs={"entity_pk": project.pk, "step": 6}
            ),
            {"selected_entities": [str(self.shareholder.pk)]},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        # Verify all data was linked
        project.refresh_from_db()
        self.assertEqual(project.product_templates.count(), 1)
        self.assertEqual(
            Stakeholder.objects.filter(parent=project, role="worker").count(), 1
        )
        self.assertEqual(
            Stakeholder.objects.filter(parent=project, role="vendor").count(), 1
        )
        self.assertEqual(
            Stakeholder.objects.filter(parent=project, role="shareholder").count(), 1
        )
