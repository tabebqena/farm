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
