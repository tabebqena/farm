"""Tests for the :class:`apps.app_base.mixins.OfficerMixin` and
:class:`apps.app_base.mixins.AmountCleanMixin` validation rules, exercised
through :class:`apps.app_operation.models.proxies.CapitalValuationOperation`.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.app_entity.models import EntityType
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CapitalValuationOperation

from .general import User, get_or_create_system, make_entity, make_officer


class OfficerMixinValidationTests(TestCase):
    """Test OfficerMixin validation"""

    def setUp(self):
        self.system = get_or_create_system()
        self.entity = make_entity("Test", EntityType.PROJECT)

    def test_clean_accepts_valid_staff_officer(self):
        """clean() should accept valid staff officer"""
        officer = make_officer()

        operation = CapitalValuationOperation(
            source=self.system,
            destination=self.entity,
            amount=Decimal("100"),
            operation_type=OperationType.CAPITAL_GAIN,
            date=timezone.now().date(),
            officer=officer,
            description="Test",
        )
        # Should not raise
        operation.clean()

    def test_clean_rejects_non_staff_officer(self):
        """clean() should reject non-staff officer"""
        user = User.objects.create_user(
            username="nonstaff", email="user@test.com", password="pass", is_staff=False
        )

        operation = CapitalValuationOperation(
            source=self.system,
            destination=self.entity,
            amount=Decimal("100"),
            operation_type=OperationType.CAPITAL_GAIN,
            date=timezone.now().date(),
            officer=user,
            description="Test",
        )

        with self.assertRaises(ValidationError):
            operation.clean()

    def test_clean_rejects_inactive_officer(self):
        """clean() should reject inactive officer"""
        user = User.objects.create_user(
            username="inactive",
            email="user@test.com",
            password="pass",
            is_staff=True,
            is_active=False,
        )

        operation = CapitalValuationOperation(
            source=self.system,
            destination=self.entity,
            amount=Decimal("100"),
            operation_type=OperationType.CAPITAL_GAIN,
            date=timezone.now().date(),
            officer=user,
            description="Test",
        )

        with self.assertRaises(ValidationError):
            operation.clean()


class AmountCleanMixinValidationTests(TestCase):
    """Test AmountCleanMixin positive amount validation"""

    def setUp(self):
        self.system = get_or_create_system()
        self.entity = make_entity("Test", EntityType.PROJECT)
        self.officer = make_officer()

    def test_clean_accepts_positive_amount(self):
        """clean() should accept positive amount"""
        operation = CapitalValuationOperation(
            source=self.system,
            destination=self.entity,
            amount=Decimal("100.00"),
            operation_type=OperationType.CAPITAL_GAIN,
            date=timezone.now().date(),
            officer=self.officer,
            description="Test",
        )
        # Should not raise
        operation.clean()

    def test_clean_rejects_zero_amount(self):
        """clean() should reject zero amount"""
        operation = CapitalValuationOperation(
            source=self.system,
            destination=self.entity,
            amount=Decimal("0.00"),
            operation_type=OperationType.CAPITAL_GAIN,
            date=timezone.now().date(),
            officer=self.officer,
            description="Test",
        )

        with self.assertRaises(ValidationError):
            operation.clean()

    def test_clean_rejects_negative_amount(self):
        """clean() should reject negative amount"""
        operation = CapitalValuationOperation(
            source=self.system,
            destination=self.entity,
            amount=Decimal("-100.00"),
            operation_type=OperationType.CAPITAL_GAIN,
            date=timezone.now().date(),
            officer=self.officer,
            description="Test",
        )

        with self.assertRaises(ValidationError):
            operation.clean()
