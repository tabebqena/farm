"""Integration: the real auto-creation paths are tagged as derived rows."""

from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.app_audit.models import SaveLog
from apps.app_base.tests.general import (
    get_or_create_system,
    make_entity,
    make_officer,
)
from apps.app_entity.models import EntityType
from apps.app_operation.models.operation_type import OperationType


@override_settings(FARM_TRACKING_ENABLED=True)
class DomainDerivedMarkerTests(TestCase):
    def setUp(self):
        self.officer = make_officer()
        self.system = get_or_create_system()
        self.entity = make_entity("Marker Entity", EntityType.PROJECT)

    def test_issuance_transaction_is_tagged_derived(self):
        from apps.app_operation.models.proxies import CorrectionOperation

        CorrectionOperation.objects.create(
            source=self.system,
            destination=self.entity,
            amount=Decimal("1000"),
            operation_type=OperationType.CORRECTION_CREDIT,
            date=timezone.now().date(),
            officer=self.officer,
            description="Marker test",
        )
        log = SaveLog.objects.filter(model="transaction", is_derived=True).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.role, "ISSUANCE_TXN")
        self.assertTrue(log.reason_text)

    def test_entity_period_creation_is_tagged_derived(self):
        logs = SaveLog.objects.filter(
            model="financialperiod", is_derived=True
        )
        self.assertTrue(logs.exists())
        self.assertEqual(logs.first().role, "PERIOD")
        self.assertTrue(logs.first().reason_text)
