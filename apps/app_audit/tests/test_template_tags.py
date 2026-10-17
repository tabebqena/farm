"""Tests for the ``audit_tags`` template helpers."""

from django.template import Context, Template
from django.test import TestCase

from apps.app_entity.models.category import FinancialCategory


class AuditTagTests(TestCase):
    def test_record_history_url_for_saved_object(self):
        category = FinancialCategory.objects.create(name="Tag", aspect="EXPENSE")
        rendered = Template(
            "{% load audit_tags %}{% record_history_url obj as u %}{{ u }}"
        ).render(Context({"obj": category}))
        self.assertIn("/audit/record/", rendered)
        self.assertIn("financialcategory", rendered)
        self.assertIn(str(category.pk), rendered)

    def test_none_object_renders_empty(self):
        rendered = Template(
            "{% load audit_tags %}{% record_history_url obj as u %}[{{ u }}]"
        ).render(Context({"obj": None}))
        self.assertEqual(rendered, "[]")
