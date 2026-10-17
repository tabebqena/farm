"""Soft-delete behaviour for :class:`Operation`.

Deleting an operation soft-deletes its ledger transactions with it. They attach
through a ``GenericForeignKey`` (content_type / object_id), so they are not a
``PROTECT`` reverse relation the delete guard can discover — without this hook
they would survive as live orphans still referencing the operation's entities.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CorrectionOperation
from apps.app_transaction.models import Transaction

User = get_user_model()


class OperationSoftDeleteTests(TestCase):
    def setUp(self):
        self.officer = User.objects.create_user(
            username="officer", password="x", is_staff=True
        )
        self.system = Entity.create(EntityType.SYSTEM)
        self.project = Entity.create(EntityType.PROJECT, name="Test Project")

    def _correction(self):
        op = CorrectionOperation(
            source=self.system,
            destination=self.project,
            amount=Decimal("10.00"),
            operation_type=OperationType.CORRECTION_CREDIT,
            date=date.today(),
            description="correction",
            officer=self.officer,
        )
        op.save()
        return op

    def test_delete_soft_deletes_linked_transactions(self):
        op = self._correction()
        self.assertEqual(op.get_all_transactions().count(), 2)

        op.delete()

        op.refresh_from_db()
        self.assertIsNotNone(op.deleted_at)
        # No live transactions remain; the tombstones stay for the audit trail.
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(Transaction.all_objects.count(), 2)
        self.assertFalse(
            Transaction.all_objects.filter(deleted_at__isnull=True).exists()
        )

    def test_deleting_operation_unblocks_its_entity(self):
        op = self._correction()
        self.assertIn("transactions", " ".join(self.project.get_delete_blockers()))

        op.delete()

        self.assertEqual(self.project.get_delete_blockers(), [])
        self.project.delete()
        self.project.refresh_from_db()
        self.assertIsNotNone(self.project.deleted_at)

    def test_reversal_transactions_are_deleted_before_their_originals(self):
        op = self._correction()
        issuance = op.get_all_transactions().get(
            type=op._issuance_transaction_type
        )
        issuance.reverse(officer=self.officer)
        # The operation itself is not reversed (only its transaction is), so the
        # guard does not block; the reversal mirror must not block the original
        # while the operation's transactions are swept.
        self.assertEqual(op.get_all_transactions().count(), 3)

        op.delete()

        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(Transaction.all_objects.count(), 3)
