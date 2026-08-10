from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import LossCoverageOperation

User = get_user_model()


def _make_officer(username):
    return User.objects.create_user(username=username, password="x", is_staff=True)


def _make_project_entity(name):
    return Entity.create(EntityType.PROJECT, name=name)


def _make_shareholder_entity(name):
    person = Entity.create(EntityType.PERSON, name=name)
    person.is_shareholder = True
    person.save()
    return person


def _make_plain_person_entity(name):
    return Entity.create(EntityType.PERSON, name=name)


class LossCoverageEntityValidationTest(TestCase):
    """Verifies the explicit clean_source / clean_destination entity-type checks
    without depending on the broken FinancialPeriod.amount fixture."""

    def setUp(self):
        self.officer = _make_officer("officer_lc_entity")
        self.project = _make_project_entity("LC Entity Project")
        self.shareholder = _make_shareholder_entity("LC Entity Shareholder")
        Stakeholder(
            parent=self.project,
            target=self.shareholder,
            role=StakeholderRole.SHAREHOLDER,
        ).save()

    def _make_op(self, **kwargs):
        defaults = dict(
            source=self.shareholder,
            destination=self.project,
            amount=Decimal("100.00"),
            operation_type=OperationType.LOSS_COVERAGE,
            date=date.today(),
            officer=self.officer,
        )
        defaults.update(kwargs)
        return LossCoverageOperation(**defaults)

    def test_clean_source_accepts_shareholder(self):
        op = self._make_op()
        # Must not raise
        op.clean_source()

    def test_clean_source_rejects_non_shareholder_person(self):
        plain = _make_plain_person_entity("Plain Person")
        op = self._make_op(source=plain)
        with self.assertRaises(ValidationError):
            op.clean_source()

    def test_clean_source_rejects_project(self):
        op = self._make_op(source=self.project)
        with self.assertRaises(ValidationError):
            op.clean_source()

    def test_clean_destination_accepts_project(self):
        op = self._make_op()
        # Must not raise
        op.clean_destination()

    def test_clean_destination_rejects_shareholder_person(self):
        op = self._make_op(destination=self.shareholder)
        with self.assertRaises(ValidationError):
            op.clean_destination()

    def test_clean_destination_rejects_system(self):
        system = Entity.create(EntityType.SYSTEM)
        op = self._make_op(destination=system)
        with self.assertRaises(ValidationError):
            op.clean_destination()
