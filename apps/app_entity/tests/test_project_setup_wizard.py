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


class ProjectSetupWizardStep4Test(TestCase):
    """Test step 4: Worker Stakeholders."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_wizard4", is_staff=True)
        self.project = Entity.create(EntityType.PROJECT, name="Wizard Project 4")

        # Create eligible workers
        self.worker1 = Entity.create(
            EntityType.PERSON, name="Worker 1", is_worker=True, active=True
        )
        self.worker2 = Entity.create(
            EntityType.PERSON, name="Worker 2", is_worker=True, active=True
        )
        self.non_worker = Entity.create(
            EntityType.PERSON, name="Not a Worker", is_worker=False, active=True
        )

    def test_wizard_step_4_get_shows_eligible_workers(self):
        """Test GET request to step 4 shows eligible workers."""
        self.client.login(username="officer_wizard4", password="testpass")
        response = self.client.get(
            reverse("project_setup_step", kwargs={"entity_pk": self.project.pk, "step": 4})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["step"], 4)
        self.assertIn(self.worker1, response.context["eligible_entities"])

    def test_wizard_step_4_adds_workers(self):
        """Test POST to step 4 creates worker stakeholders."""
        self.client.login(username="officer_wizard4", password="testpass")
        response = self.client.post(
            reverse("project_setup_step", kwargs={"entity_pk": self.project.pk, "step": 4}),
            {
                "selected_entities": [str(self.worker1.pk), str(self.worker2.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)
        stakeholders = Stakeholder.objects.filter(parent=self.project, role="worker")
        self.assertEqual(stakeholders.count(), 2)


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
