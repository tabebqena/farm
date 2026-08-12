from datetime import date

from django.test import TestCase

from apps.app_animal.models import MedicalRecord
from apps.app_entity.models import EntityType
from apps.app_inventory.tests.general import make_entity, make_product, make_product_template


class MedicalRecordTest(TestCase):
    def setUp(self):
        self.entity = make_entity(EntityType.PROJECT)
        self.template = make_product_template()
        self.product = make_product(self.template, entity=self.entity)

    def test_create_and_reverse_relation(self):
        rec = MedicalRecord.objects.create(
            product=self.product,
            date=date(2026, 1, 1),
            record_type=MedicalRecord.RecordType.VACCINATION,
            status=MedicalRecord.HealthStatus.HEALTHY,
            next_due_date=date(2026, 2, 1),
            notes="Annual vaccine",
        )
        self.assertIn(rec, self.product.medical_records.all())
        self.assertEqual(self.product.medical_records.count(), 1)
        self.assertEqual(rec.get_record_type_display(), "Vaccination")

    def test_default_status_unknown(self):
        rec = MedicalRecord.objects.create(
            product=self.product,
            date=date(2026, 1, 1),
            record_type=MedicalRecord.RecordType.CHECKUP,
        )
        self.assertEqual(rec.status, MedicalRecord.HealthStatus.UNKNOWN)
