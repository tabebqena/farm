from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import (
    CashInjectionOperation,
    InternalTransferOperation,
)
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


def _make_officer(username="officer"):
    return User.objects.create_user(
        username=username, password="testpass", is_staff=True
    )


def _make_internal_person(name):
    person = Entity.create(EntityType.PERSON, name=name, is_internal=True)
    return person


def _inject(world_entity, dest_entity, amount, officer):
    CashInjectionOperation(
        source=world_entity,
        destination=dest_entity,
        amount=amount,
        operation_type=OperationType.CASH_INJECTION,
        date=date.today(),
        description="Seed balance",
        officer=officer,
    ).save()


class InternalTransferGetRelatedEntitiesTest(TestCase):
    """
    Tests for get_related_entities — the method that populates the destination
    dropdown on the create form.  Only internal Person entities (excluding the
    url_entity itself) should be eligible destinations.
    """

    def setUp(self):
        self.world_entity = Entity.create(EntityType.WORLD)
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.url_entity = _make_internal_person("Source Person")

        self.other_internal = _make_internal_person("Other Internal Person")
        self.external_person = Entity.create(EntityType.PERSON, name="External Person")

        self.project_entity = Entity.create(EntityType.PROJECT, name="Test Project")

        # config mirrors what resolve_request produces for internal transfer
        self.config = {"source": "url", "dest": "post"}

    def test_returns_all_person_entities_except_url_entity(self):
        result = InternalTransferOperation.get_related_entities(
            self.url_entity, self.config
        )
        self.assertIn(self.other_internal, result)
        self.assertIn(self.external_person, result)

    def test_excludes_url_entity_itself(self):
        result = InternalTransferOperation.get_related_entities(
            self.url_entity, self.config
        )
        self.assertNotIn(self.url_entity, result)

    def test_excludes_world_entity(self):
        result = InternalTransferOperation.get_related_entities(
            self.url_entity, self.config
        )
        self.assertNotIn(self.world_entity, result)

    def test_excludes_system_entity(self):
        result = InternalTransferOperation.get_related_entities(
            self.url_entity, self.config
        )
        self.assertNotIn(self.system_entity, result)

    def test_excludes_project_entity(self):
        result = InternalTransferOperation.get_related_entities(
            self.url_entity, self.config
        )
        self.assertNotIn(self.project_entity, result)
