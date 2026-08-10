"""
Comprehensive tests for app_base models, mixins, and managers.
Tests BaseModel and ReversableModel using concrete models from the codebase.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.app_base.management.commands.seed import ANIMAL_TEMPLATES
from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.models import ProductTemplate
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CapitalGainOperation

User = get_user_model()


# =============================================================================
# Fixtures / Helpers
# =============================================================================


def _make_officer(username="officer"):
    return User.objects.create_user(
        username=username, email=f"{username}@test.com", password="pass", is_staff=True
    )


def _make_entity(name, entity_type=EntityType.PERSON):
    return Entity.create(entity_type, name=name)


def _get_or_create_system():
    """Get or create system entity"""
    try:
        return Entity.objects.get(entity_type=EntityType.SYSTEM)
    except Entity.DoesNotExist:
        return Entity.create(EntityType.SYSTEM)


# =============================================================================
# BaseModel Timestamp Tests (using Entity model)
# =============================================================================


class BaseModelTimestampTests(TestCase):
    """Test BaseModel created_at and updated_at automatic fields"""

    def test_created_at_set_automatically(self):
        """created_at should be set automatically on save"""
        before = timezone.now()
        entity = _make_entity("Test Entity")
        after = timezone.now()

        self.assertIsNotNone(entity.created_at)
        self.assertGreaterEqual(entity.created_at, before)
        self.assertLessEqual(entity.created_at, after)

    def test_updated_at_set_on_creation(self):
        """updated_at should be set on new objects"""
        entity = _make_entity("Test Entity")
        self.assertIsNotNone(entity.updated_at)

    def test_created_at_unchanged_on_update(self):
        """created_at should not change when object is updated"""
        entity = _make_entity("Test Entity")
        original_created_at = entity.created_at

        # Change something else
        entity.active = False
        entity.save()
        entity.refresh_from_db()

        self.assertEqual(entity.created_at, original_created_at)

    def test_updated_at_changes_on_update(self):
        """updated_at should change when object is updated"""
        entity = _make_entity("Test Entity")
        original_updated_at = entity.updated_at

        # Change and save
        entity.active = False
        entity.save()
        entity.refresh_from_db()

        self.assertGreaterEqual(entity.updated_at, original_updated_at)


# =============================================================================
# BaseModel Deletion Tests
# =============================================================================


class BaseModelDeletableFieldTests(TestCase):
    """Test BaseModel deletable field behavior"""

    def test_deletable_defaults_to_false(self):
        """New objects should have deletable=False by default"""
        entity = _make_entity("Test Entity")
        self.assertFalse(entity.deletable)

    def test_deleted_at_initially_null(self):
        """deleted_at should be NULL for new objects"""
        entity = _make_entity("Test Entity")
        self.assertIsNone(entity.deleted_at)


# =============================================================================
# ActiveManager Tests
# =============================================================================


class ActiveManagerTests(TestCase):
    """Test ActiveManager excludes soft-deleted items"""

    def test_objects_manager_is_active_manager(self):
        """default objects manager should be ActiveManager"""
        entity = _make_entity("Active")

        # Using active manager
        self.assertGreaterEqual(Entity.objects.count(), 1)
        self.assertIn(entity, Entity.objects.all())

    def test_all_objects_returns_all(self):
        """all_objects manager should return all items"""
        entity1 = _make_entity("Entity1")
        entity2 = _make_entity("Entity2")

        # Using all_objects
        all_entities = Entity.all_objects.filter(name__in=["Entity1", "Entity2"])
        self.assertEqual(all_entities.count(), 2)


# =============================================================================
# SafeQuerySet Tests
# =============================================================================


class SafeQuerySetTests(TestCase):
    """Test SafeQuerySet restrictions on bulk operations"""

    def test_direct_update_is_blocked(self):
        """QuerySet.update() should raise NotImplementedError"""
        entity = _make_entity("Test")

        with self.assertRaises(NotImplementedError):
            Entity.objects.filter(pk=entity.pk).update(active=False)

    def test_bulk_create_is_blocked(self):
        """QuerySet.bulk_create() should raise NotImplementedError"""
        entities = [Entity(name=f"Entity{i}", entity_type=EntityType.PERSON) for i in range(3)]

        with self.assertRaises(NotImplementedError):
            Entity.objects.bulk_create(entities)


# =============================================================================
# Transaction Model Tests via CapitalGainOperation
# =============================================================================


class TransactionAutoCreationTests(TestCase):
    """Test that operations auto-create transactions (BaseModel linked models)"""

    def setUp(self):
        self.officer = _make_officer()
        self.system = _get_or_create_system()
        self.entity = _make_entity("Test Entity", EntityType.PROJECT)

    def test_capital_gain_creates_transaction(self):
        """CapitalGainOperation should auto-create transaction"""
        from apps.app_transaction.models import Transaction

        operation = CapitalGainOperation.objects.create(
            source=self.system,
            destination=self.entity,
            amount=Decimal("1000"),
            operation_type=OperationType.CAPITAL_GAIN,
            date=timezone.now().date(),
            officer=self.officer,
            description="Test",
        )

        # Should have created transaction(s)
        txs = Transaction.objects.filter(object_id=operation.pk)
        self.assertGreater(txs.count(), 0)

    def test_operation_has_timestamps(self):
        """Operation (extends BaseModel) should have timestamps"""
        operation = CapitalGainOperation.objects.create(
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


# =============================================================================
# OfficerMixin Validation Tests
# =============================================================================


class OfficerMixinValidationTests(TestCase):
    """Test OfficerMixin validation"""

    def setUp(self):
        self.system = _get_or_create_system()
        self.entity = _make_entity("Test", EntityType.PROJECT)

    def test_clean_accepts_valid_staff_officer(self):
        """clean() should accept valid staff officer"""
        officer = _make_officer()

        operation = CapitalGainOperation(
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

        operation = CapitalGainOperation(
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

        operation = CapitalGainOperation(
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


# =============================================================================
# AmountCleanMixin Validation Tests
# =============================================================================


class AmountCleanMixinValidationTests(TestCase):
    """Test AmountCleanMixin positive amount validation"""

    def setUp(self):
        self.system = _get_or_create_system()
        self.entity = _make_entity("Test", EntityType.PROJECT)
        self.officer = _make_officer()

    def test_clean_accepts_positive_amount(self):
        """clean() should accept positive amount"""
        operation = CapitalGainOperation(
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
        operation = CapitalGainOperation(
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
        operation = CapitalGainOperation(
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


# =============================================================================
# Post-Save Task Dispatch Tests
# =============================================================================


class PostSaveTaskDispatchTests(TestCase):
    """Test BaseModel.post_save() task execution"""

    def test_post_save_tasks_are_executed(self):
        """post_save_tasks should be executed after save"""
        executed = []

        def dummy_task(arg):
            executed.append(arg)

        entity = Entity(name="Test", entity_type=EntityType.PERSON)
        entity.save(post_save_tasks=[(dummy_task, ("test",), {})])

        self.assertEqual(executed, ["test"])

    def test_post_save_with_kwargs(self):
        """post_save_tasks should work with keyword arguments"""
        executed = []

        def dummy_task(arg1, arg2=None):
            executed.append((arg1, arg2))

        entity = Entity(name="Test", entity_type=EntityType.PERSON)
        entity.save(post_save_tasks=[(dummy_task, ("test",), {"arg2": "kwarg"})])

        self.assertEqual(executed, [("test", "kwarg")])


# =============================================================================
# Seed Command Tests
# =============================================================================


class SeedCommandProductTemplatesTest(TestCase):
    """The seed command must create the species × stage × gender animal
    templates (Cow / Buffalo / Sheep / Goat) with the new animal attributes,
    prune the removed templates, and be idempotent."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed")

    @staticmethod
    def _name(entry):
        return f"{entry['animal_type']} {entry['stage']} {entry['gender'].title()}"

    def test_all_animal_templates_created_with_attributes(self):
        for entry in ANIMAL_TEMPLATES:
            with self.subTest(entry=self._name(entry)):
                t = ProductTemplate.objects.get(name=self._name(entry))
                self.assertEqual(t.nature, ProductTemplate.Nature.ANIMAL)
                self.assertEqual(t.animal_type, entry["animal_type"])
                self.assertEqual(t.gender, entry["gender"])
                self.assertEqual(t.tag_prefix, entry["tag_prefix"])
                self.assertTrue(t.has_tag)
                self.assertTrue(t.can_die)
                self.assertFalse(t.can_be_consumed)
                self.assertEqual(
                    set(t.produces.values_list("name", flat=True)),
                    set(entry["produces"]),
                )

    def test_only_four_species_are_seeded(self):
        """No ANIMAL template exists outside Cow/Buffalo/Sheep/Goat."""
        self.assertEqual(
            ProductTemplate.objects.filter(nature=ProductTemplate.Nature.ANIMAL).count(),
            len(ANIMAL_TEMPLATES),
        )

    def test_gives_birth_to_resolution(self):
        expected = {
            "Cow Adult Female": "Cow Calf Female",
            "Buffalo Adult Female": "Buffalo Calf Female",
            "Sheep Adult Female": "Sheep Calf Female",
            "Goat Adult Female": "Goat Calf Female",
        }
        for source, target in expected.items():
            with self.subTest(source=source):
                self.assertEqual(
                    ProductTemplate.objects.get(name=source).gives_birth_to.name,
                    target,
                )
        # Male and calf templates never give birth.
        for name in (
            "Cow Adult Male",
            "Cow Calf Male",
            "Cow Calf Female",
            "Buffalo Adult Male",
            "Buffalo Calf Male",
            "Sheep Calf Female",
            "Goat Adult Male",
            "Goat Calf Female",
        ):
            with self.subTest(name=name):
                self.assertIsNone(ProductTemplate.objects.get(name=name).gives_birth_to)

    def test_removed_templates_are_not_created(self):
        removed = [
            "Fattening Cattle",
            "Dairy Cows",
            "Breeding Bulls",
            "Replacement Heifers",
            "Calves",
            "Fattening Lambs",
            "Breeding Ewes",
            "Breeding Rams",
            "Fattening Kids",
            "Breeding Does",
            "Breeding Bucks",
            "Fattening Camels (Hashi)",
            "Horses",
            "Donkeys / Mules",
            "Broiler Chickens",
            "Laying Hens",
            "Fattening Turkeys",
            "Fattening Ducks / Geese",
            "Fattening Rabbits",
            "Breeding Rabbits",
        ]
        for name in removed:
            with self.subTest(name=name):
                self.assertFalse(
                    ProductTemplate.objects.filter(name=name).exists(),
                    f"{name!r} should not be seeded",
                )

    def test_non_animal_templates_have_no_animal_flags(self):
        for t in ProductTemplate.objects.exclude(nature=ProductTemplate.Nature.ANIMAL):
            self.assertFalse(t.can_die)
            self.assertTrue(t.can_be_consumed)
            self.assertEqual(t.gender, ProductTemplate.Gender.NA)

    def test_seed_is_idempotent(self):
        before = ProductTemplate.objects.count()
        call_command("seed")  # must not raise
        self.assertEqual(ProductTemplate.objects.count(), before)
