"""
QuerySet operation logging for tracking bulk operations, deletions, and updates.
Extends Django's QuerySet with comprehensive logging for data modifications.
"""

import logging
from typing import Any, Dict, Optional

from django.db.models import QuerySet

from apps.app_base.debug import DebugContext

logger = logging.getLogger(__name__)


class LoggingQuerySet(QuerySet):
    """QuerySet subclass with comprehensive operation logging."""

    def _log_operation(self, operation: str, count: int, filters: Optional[Dict[str, Any]] = None):
        """Log a QuerySet operation."""
        model_name = self.model.__name__
        data = {
            "model": model_name,
            "operation": operation,
            "affected_count": count,
        }
        if filters:
            data["filters"] = str(filters)[:200]  # Limit filter string length

        DebugContext.log(f"QuerySet.{operation}", data, level="debug")

    def delete(self):
        """Log all delete operations."""
        model_name = self.model.__name__
        count, _ = super().delete()

        DebugContext.warn(f"Bulk delete on {model_name}", {
            "count": count,
            "filters": str(self.query)[:200],
        })

        # Audit log all deletions
        DebugContext.audit(
            action="bulk_delete",
            entity_type=model_name,
            entity_id=None,
            details={"count": count, "filters": str(self.query)[:200]},
            user="system"
        )

        return count, _

    def update(self, **kwargs):
        """Log all update operations."""
        model_name = self.model.__name__
        count = super().update(**kwargs)

        self._log_operation("update", count, kwargs)

        # Audit log all updates
        DebugContext.audit(
            action="bulk_update",
            entity_type=model_name,
            entity_id=None,
            details={"count": count, "fields_updated": list(kwargs.keys())},
            user="system"
        )

        return count

    def create(self, **kwargs):
        """Log create operation (for consistency)."""
        model_name = self.model.__name__
        instance = super().create(**kwargs)

        DebugContext.log(f"QuerySet.create", {
            "model": model_name,
            "pk": instance.pk,
        })

        return instance

    def bulk_create(self, objs, **kwargs):
        """Log bulk_create operations."""
        model_name = self.model.__name__
        objs_list = list(objs)  # Convert in case it's a generator
        count = len(objs_list)

        instances = super().bulk_create(objs_list, **kwargs)

        DebugContext.log(f"QuerySet.bulk_create", {
            "model": model_name,
            "count": count,
            "batch_size": kwargs.get("batch_size", "default"),
        })

        # Audit log bulk creations
        DebugContext.audit(
            action="bulk_create",
            entity_type=model_name,
            entity_id=None,
            details={"count": count},
            user="system"
        )

        return instances

    def bulk_update(self, objs, fields, **kwargs):
        """Log bulk_update operations."""
        model_name = self.model.__name__
        objs_list = list(objs)
        count = len(objs_list)

        result = super().bulk_update(objs_list, fields, **kwargs)

        DebugContext.log(f"QuerySet.bulk_update", {
            "model": model_name,
            "count": count,
            "fields": fields,
        })

        # Audit log bulk updates
        DebugContext.audit(
            action="bulk_update",
            entity_type=model_name,
            entity_id=None,
            details={"count": count, "fields": fields},
            user="system"
        )

        return result


class LoggingManager(logging.Manager):
    """Manager that uses LoggingQuerySet for all queries."""

    def get_queryset(self):
        """Return a LoggingQuerySet."""
        return LoggingQuerySet(self.model, using=self._db)

    def all(self):
        """Override all to use logging."""
        return self.get_queryset()

    def filter(self, *args, **kwargs):
        """Override filter to use logging."""
        return self.get_queryset().filter(*args, **kwargs)

    def exclude(self, *args, **kwargs):
        """Override exclude to use logging."""
        return self.get_queryset().exclude(*args, **kwargs)

    def get(self, *args, **kwargs):
        """Override get to use logging."""
        return self.get_queryset().get(*args, **kwargs)

    def create(self, **kwargs):
        """Override create to use logging."""
        return self.get_queryset().create(**kwargs)

    def bulk_create(self, objs, **kwargs):
        """Override bulk_create to use logging."""
        return self.get_queryset().bulk_create(objs, **kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        """Override bulk_update to use logging."""
        return self.get_queryset().bulk_update(objs, fields, **kwargs)

    def update(self, **kwargs):
        """Override update to use logging."""
        return self.get_queryset().update(**kwargs)

    def delete(self):
        """Override delete to use logging."""
        return self.get_queryset().delete()
