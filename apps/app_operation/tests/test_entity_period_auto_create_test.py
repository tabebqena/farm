from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import QuerySet as DjangoQuerySet
from django.test import TestCase
from apps.app_entity.models import Entity, EntityType
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.period import FinancialPeriod
from apps.app_operation.models.proxies import CashInjectionOperation

User = get_user_model()

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)
LAST_MONTH = TODAY - timedelta(days=30)
NEXT_MONTH = TODAY + timedelta(days=30)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_officer():
    return User.objects.create_user(username="officer_fp", password="x", is_staff=True)


def _make_person_entity(name="Receiver"):
    return Entity.create(EntityType.PERSON, name=name)


def _make_world_entity():
    return Entity.create(EntityType.WORLD)


# ---------------------------------------------------------------------------
# FinancialPeriod model tests
# ---------------------------------------------------------------------------



class EntityPeriodAutoCreateTest(TestCase):

    def test_new_person_entity_gets_period(self):
        entity = Entity.create(EntityType.PERSON, name="Auto Period Person")
        self.assertEqual(FinancialPeriod.objects.filter(entity=entity).count(), 1)

    def test_new_project_entity_gets_period(self):
        project = Entity.create(EntityType.PROJECT, name="Auto Period Project")
        project.save()
        entity = project
        self.assertEqual(FinancialPeriod.objects.filter(entity=entity).count(), 1)

    def test_world_entity_does_not_get_period(self):
        entity = Entity.create(EntityType.WORLD)
        self.assertEqual(FinancialPeriod.objects.filter(entity=entity).count(), 0)

    def test_system_entity_does_not_get_period(self):
        entity = Entity.create(EntityType.SYSTEM)
        self.assertEqual(FinancialPeriod.objects.filter(entity=entity).count(), 0)

    def test_period_start_date_equals_entity_creation_date(self):
        entity = Entity.create(EntityType.PERSON, name="Date Check Person")
        period = FinancialPeriod.objects.get(entity=entity)
        self.assertEqual(period.start_date, entity.created_at.date())


# ---------------------------------------------------------------------------
# Operation period assignment and validation
# ---------------------------------------------------------------------------
