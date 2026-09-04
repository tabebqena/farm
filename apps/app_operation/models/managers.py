"""Custom querysets and managers for operations.

Provides :class:`OperationQuerySet` (which blocks bulk ``update`` /
``bulk_create`` so operations only change through validated saves) together with
the default and all-objects managers used by :class:`Operation`.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class OperationQuerySet(models.QuerySet):
    """QuerySet that blocks bulk writes and can re-cast rows to proxies.

    Bulk ``update`` / ``bulk_create`` raise; ``delete`` soft-deletes each row
    individually (no bulk hard delete); :meth:`cast` re-types each result into
    its operation proxy subclass.
    """

    def update(self, **kwargs):
        """Block direct bulk updates; require validated individual saves."""
        raise NotImplementedError(
            _("Direct .update() is blocked. Use individual .save() for validation.")
        )

    def bulk_create(self, objs, **kwargs):
        """Block bulk creation; require validated individual saves."""
        raise NotImplementedError(
            _("Direct .bulk_create() is blocked. Save objects individually.")
        )

    def delete(self):
        """Soft-delete every operation in the queryset, one row at a time.

        No bulk hard delete: each operation is individually soft-deleted so the
        operation ``delete()`` hooks and validation still run. Returns the
        Django-style ``(count, {model_label: count})`` tuple.
        """
        count = 0
        for obj in self:
            obj.delete()
            count += 1
        return count, {self.model._meta.label: count}

    def cast(self):
        """
        Re-casts each Operation instance in the queryset to its correct proxy subclass.
        Call this when you need type-specific behavior on query results.
        Usage: Operation.objects.filter(...).cast()
        """
        from apps.app_operation.models.proxies import PROXY_MAP

        results = list(self)
        for obj in results:
            proxy_cls = PROXY_MAP.get(obj.operation_type)
            if proxy_cls:
                obj.__class__ = proxy_cls
        return results


class OperationManager(models.Manager):
    """Default manager: non-soft-deleted operations, with proxy casting."""

    def get_queryset(self):
        """Return non-soft-deleted operations only."""
        return OperationQuerySet(self.model, using=self._db).filter(
            deleted_at__isnull=True
        )

    def cast(self, instance):
        """Cast a single Operation instance to its proxy subclass."""
        from apps.app_operation.models.proxies import PROXY_MAP

        proxy_cls = PROXY_MAP.get(instance.operation_type)
        if proxy_cls:
            instance.__class__ = proxy_cls
        return instance


class AllOperationManager(models.Manager):
    """Manager that includes soft-deleted records."""

    def get_queryset(self):
        """Return all operations, including soft-deleted ones."""
        return OperationQuerySet(self.model, using=self._db)
