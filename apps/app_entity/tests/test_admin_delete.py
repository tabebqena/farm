"""Django-admin delete integration with the soft-delete guard.

Django admin's delete collector refuses to delete a parent while **any** row —
soft-deleted tombstones included — references it through a ``PROTECT`` FK. Under
this project's soft-delete conventions that is wrong: tombstones and
``_delete_auto_relations`` rows must not block. ``SoftDeleteAdminGuardMixin``
re-points the admin delete decision at ``get_delete_blockers()``.
"""

from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType
from apps.app_operation.models.operation import Operation
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CorrectionOperation

User = get_user_model()


class AdminDeleteGuardTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="root", password="x", email="root@example.test"
        )
        self.client.force_login(self.superuser)
        self.system = Entity.create(EntityType.SYSTEM)
        self.entity = Entity.create(EntityType.PROJECT, name="Admin Delete Project")

    @staticmethod
    def _delete_url(model, pk):
        return reverse(
            f"admin:{model._meta.app_label}_{model._meta.model_name}_delete",
            args=[pk],
        )

    def _correction(self):
        op = CorrectionOperation(
            source=self.system,
            destination=self.entity,
            amount=Decimal("10.00"),
            operation_type=OperationType.CORRECTION_CREDIT,
            date=date.today(),
            description="correction",
            officer=self.superuser,
        )
        op.save()
        return op

    def test_bare_entity_is_deletable_from_admin(self):
        """The auto-created financial period must not block the admin delete."""
        url = self._delete_url(Entity, self.entity.pk)

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Cannot delete")

        response = self.client.post(url, {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.entity.refresh_from_db()
        self.assertIsNotNone(self.entity.deleted_at)

    def test_tombstoned_owned_row_does_not_block_admin_delete(self):
        """A soft-deleted period (tombstone) must not block the entity delete."""
        period = self.entity.financial_periods.get()
        period.delete()

        url = self._delete_url(Entity, self.entity.pk)
        response = self.client.get(url)
        self.assertNotContains(response, "Cannot delete")

        response = self.client.post(url, {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.entity.refresh_from_db()
        self.assertIsNotNone(self.entity.deleted_at)

    def test_live_operation_still_blocks_admin_delete(self):
        self._correction()
        url = self._delete_url(Entity, self.entity.pk)

        response = self.client.get(url)
        self.assertContains(response, "Cannot delete")

        response = self.client.post(url, {"post": "yes"})
        self.entity.refresh_from_db()
        self.assertIsNone(self.entity.deleted_at)

    def test_entity_deletable_after_operation_deleted_via_admin(self):
        op = self._correction()

        op_url = self._delete_url(Operation, op.pk)
        response = self.client.post(op_url, {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        op.refresh_from_db()
        self.assertIsNotNone(op.deleted_at)

        entity_url = self._delete_url(Entity, self.entity.pk)
        response = self.client.get(entity_url)
        self.assertNotContains(response, "Cannot delete")
        response = self.client.post(entity_url, {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.entity.refresh_from_db()
        self.assertIsNotNone(self.entity.deleted_at)

    def test_guard_error_is_reported_not_a_500(self):
        """A guard refusal on the confirming request is messaged, not raised."""
        url = self._delete_url(Entity, self.entity.pk)
        with mock.patch.object(
            Entity, "delete", side_effect=ValidationError("live dependents")
        ):
            response = self.client.post(url, {"post": "yes"})

        self.assertEqual(response.status_code, 302)
        self.entity.refresh_from_db()
        self.assertIsNone(self.entity.deleted_at)
