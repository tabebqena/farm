"""Ownership guard for the evaluation (CAPITAL_GAIN / CAPITAL_LOSS) flow.

Regression tests for the wrong-ownership gap: the evaluation form previously
filtered products by *template assignment* instead of by *product owner*
(``product.entity``), so a product owned by another entity (but sharing a
template) could be evaluated. See ai-plans/improve-operation-test-suite-plan.md
§13.
"""
from datetime import date
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.models import Product, ProductTemplate
from apps.app_inventory.tests.general import make_user
from apps.app_operation.models.operation import Operation
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.views.create_operation.evaluation import EvaluationForm


class EvaluationOwnershipTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_eval", is_staff=True)
        self.project_a = Entity.create(EntityType.PROJECT, name="Farm A")
        self.project_b = Entity.create(EntityType.PROJECT, name="Farm B")
        self.template = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            tracking_mode=ProductTemplate.TrackingMode.INDIVIDUAL,
            default_unit="Head",
        )
        # The template is assigned to BOTH projects — the ownership bug was that
        # the form used template assignment instead of product.entity.
        self.template.entities.add(self.project_a, self.project_b)
        self.product_a = Product.objects.create(
            product_template=self.template,
            entity=self.project_a,
            unit_price=Decimal("100.00"),
        )
        self.product_b = Product.objects.create(
            product_template=self.template,
            entity=self.project_b,
            unit_price=Decimal("100.00"),
        )

    def test_evaluation_form_restricts_products_to_owned_entity(self):
        """The evaluation form only offers products owned by the project."""
        form = EvaluationForm(project=self.project_a)
        qs = form.fields["product"].queryset
        self.assertIn(self.product_a, qs)
        self.assertNotIn(self.product_b, qs)

        form_b = EvaluationForm(project=self.project_b)
        qs_b = form_b.fields["product"].queryset
        self.assertIn(self.product_b, qs_b)
        self.assertNotIn(self.product_a, qs_b)

    def test_evaluation_post_rejects_other_project_product(self):
        """Posting a product owned by another project creates no capital op."""
        self.client.login(username="officer_eval", password="testpass")
        url = reverse(
            "evaluation_create_view",
            kwargs={"pk": self.project_a.pk, "product_pk": self.product_b.pk},
        )
        response = self.client.post(
            url,
            {
                "product": str(self.product_b.pk),
                "new_unit_price": "150.00",
                "date": date.today().isoformat(),
                "description": "",
            },
        )
        # The form is re-rendered (invalid choice) and nothing is persisted.
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Operation.objects.filter(
                operation_type__in=[
                    OperationType.CAPITAL_GAIN,
                    OperationType.CAPITAL_LOSS,
                ]
            ).exists()
        )

    def test_evaluation_post_accepts_owned_product_form(self):
        """A product owned by the project passes the form-level ownership check."""
        form = EvaluationForm(
            project=self.project_a,
            data={
                "product": str(self.product_a.pk),
                "new_unit_price": "150.00",
                "date": date.today().isoformat(),
                "description": "",
            },
        )
        self.assertTrue(form.is_valid(), form.errors)
