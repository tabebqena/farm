"""Tests that BaseModel-backed operations auto-create their related
transactions, exercised through concrete operation proxies.
"""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.app_entity.models import EntityType
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CapitalValuationOperation

from .general import get_or_create_system, make_entity, make_officer


class TransactionAutoCreationTests(TestCase):
    """Test that operations auto-create transactions (BaseModel linked models)"""

    def setUp(self):
        self.officer = make_officer()
        self.system = get_or_create_system()
        self.entity = make_entity("Test Entity", EntityType.PROJECT)

    def test_correction_credit_creates_transaction(self):
        """CorrectionOperation should auto-create transaction"""
        from apps.app_transaction.models import Transaction
        from apps.app_operation.models.proxies import CorrectionOperation

        operation = CorrectionOperation.objects.create(
            source=self.system,
            destination=self.entity,
            amount=Decimal("1000"),
            operation_type=OperationType.CORRECTION_CREDIT,
            date=timezone.now().date(),
            officer=self.officer,
            description="Test",
        )

        # Should have created transaction(s)
        txs = Transaction.objects.filter(object_id=operation.pk)
        self.assertGreater(txs.count(), 0)

    def test_operation_has_timestamps(self):
        """Operation (extends BaseModel) should have timestamps"""
        operation = CapitalValuationOperation.objects.create(
            source=self.system,
            destination=self.entity,
            amount=Decimal("1000"),
            operation_type=OperationType.CAPITAL_GAIN,
            date=timezone.now().date(),
            officer=self.officer,
            description="Test",
        )

        self.assertIsNotNone(operation.created_at)
        self.assertIsNotNone(operation.updated_at)
