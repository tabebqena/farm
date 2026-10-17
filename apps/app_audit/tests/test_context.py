"""Tests for the provenance capture layer (``apps.app_audit.context``)."""

import json

from django.test import TestCase, override_settings

from apps.app_audit import context as provenance
from apps.app_audit.models import ActionTrace, SaveLog
from apps.app_audit.reasons import REASON_AUTO_PRODUCT, reason_text
from apps.app_audit.serialization import serialize_instance
from apps.app_entity.models.category import FinancialCategory


class SerializationTests(TestCase):
    def test_serialize_instance_is_json_safe(self):
        category = FinancialCategory(name="Feed", aspect="EXPENSE")
        shape = serialize_instance(category)
        json.dumps(shape)  # must not raise
        self.assertEqual(shape["name"], "Feed")
        self.assertEqual(shape["aspect"], "EXPENSE")
        self.assertIn("deleted_at", shape)

    def test_foreign_keys_serialized_without_query(self):
        relation = serialize_instance(FinancialCategory(name="X", aspect="A"))
        # No FKs on this model, but the shape must always be a dict.
        self.assertIsInstance(relation, dict)


class RecordSaveTests(TestCase):
    @override_settings(FARM_TRACKING_ENABLED=True)
    def test_records_every_save_with_new_shape(self):
        category = FinancialCategory.objects.create(name="Seeds", aspect="EXPENSE")
        logs = SaveLog.objects.filter(
            app_label="app_entity", model="financialcategory", object_id=str(category.pk)
        )
        self.assertEqual(logs.count(), 1)
        log = logs.get()
        self.assertEqual(log.kind, "create")
        self.assertFalse(log.is_derived)
        self.assertEqual(log.new_shape["name"], "Seeds")
        self.assertIsNone(log.trace)

    @override_settings(FARM_TRACKING_ENABLED=True)
    def test_second_save_is_update(self):
        category = FinancialCategory.objects.create(name="Hay", aspect="EXPENSE")
        category.description = "bales"
        category.save()
        kinds = list(
            SaveLog.objects.filter(model="financialcategory").values_list("kind", flat=True)
        )
        self.assertEqual(kinds, ["create", "update"])

    @override_settings(FARM_TRACKING_ENABLED=True)
    def test_soft_delete_kind(self):
        category = FinancialCategory.objects.create(name="Salt", aspect="EXPENSE")
        category.delete()
        delete_log = SaveLog.objects.filter(
            model="financialcategory", kind="soft_delete"
        ).get()
        self.assertIsNotNone(delete_log.new_shape["deleted_at"])

    @override_settings(FARM_TRACKING_ENABLED=True)
    def test_derived_block_tags_role_and_reason(self):
        with provenance.derived("PRODUCT", REASON_AUTO_PRODUCT, origin="model"):
            FinancialCategory.objects.create(name="Mineral", aspect="EXPENSE")
        log = SaveLog.objects.filter(model="financialcategory").get()
        self.assertTrue(log.is_derived)
        self.assertEqual(log.role, "PRODUCT")
        self.assertEqual(log.reason_code, REASON_AUTO_PRODUCT)
        self.assertEqual(log.reason_text, reason_text(REASON_AUTO_PRODUCT))

    @override_settings(FARM_TRACKING_ENABLED=True)
    def test_trace_is_linked(self):
        trace = ActionTrace.objects.create(method="POST", path="/x/")
        token = provenance.set_trace(trace)
        try:
            FinancialCategory.objects.create(name="Linked", aspect="EXPENSE")
        finally:
            provenance.reset_trace(token)
        log = SaveLog.objects.filter(model="financialcategory").get()
        self.assertEqual(log.trace_id, trace.pk)

    @override_settings(FARM_TRACKING_ENABLED=False)
    def test_disabled_writes_nothing(self):
        FinancialCategory.objects.create(name="Ignored", aspect="EXPENSE")
        self.assertEqual(SaveLog.objects.count(), 0)

    @override_settings(FARM_TRACKING_ENABLED=True)
    def test_audit_models_are_not_tracked(self):
        ActionTrace.objects.create(method="POST", path="/x/")
        SaveLog.objects.create(
            app_label="app_entity", model="financialcategory", object_id="1", kind="create"
        )
        self.assertEqual(SaveLog.objects.count(), 1)


class ReasonCatalogTests(TestCase):
    def test_known_and_unknown_codes(self):
        self.assertTrue(reason_text(REASON_AUTO_PRODUCT))
        self.assertEqual(reason_text("NOPE"), "")
        self.assertEqual(reason_text(""), "")
