"""Custom querysets and managers for operations.

Provides :class:`OperationQuerySet` (which blocks bulk ``update`` /
``bulk_create`` so operations only change through validated saves) together with
the default and all-objects managers used by :class:`Operation`.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class OperationQuerySet(models.QuerySet):
    """QuerySet that blocks bulk writes and can re-cast rows to proxies.

    Bulk ``update`` / ``bulk_create`` / ``delete`` raise (``delete`` is allowed
    when ``DEBUG`` is on); :meth:`cast` re-types each result into its operation
    proxy subclass.
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
        """Block bulk deletes outside ``DEBUG``."""
        if settings.DEBUG:
            return super().delete()
        raise NotImplementedError(_("Bulk delete is blocked."))

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
