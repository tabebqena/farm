"""Shared fixtures for ``app_base`` tests.

The builders several ``test_*.py`` modules need (staff officer, entity, system
entity) live here so each module imports only what it uses — mirroring the
``general.py`` helper pattern used by ``app_inventory`` / ``app_operation``.
"""

from django.contrib.auth import get_user_model

from apps.app_entity.models import Entity, EntityType

User = get_user_model()


def make_officer(username="officer"):
    """An active staff user allowed to act as an officer."""
    return User.objects.create_user(
        username=username, email=f"{username}@test.com", password="pass", is_staff=True
    )


def make_entity(name, entity_type=EntityType.PERSON):
    """Create an entity of the given type (defaults to PERSON)."""
    return Entity.create(entity_type, name=name)


def get_or_create_system():
    """Get or create the single system entity."""
    try:
        return Entity.objects.get(entity_type=EntityType.SYSTEM)
    except Entity.DoesNotExist:
        return Entity.create(EntityType.SYSTEM)
