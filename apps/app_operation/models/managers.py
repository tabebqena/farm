from django.conf import settings
from django.db import models


class OperationQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise NotImplementedError(
            "Direct .update() is blocked. Use individual .save() for validation."
        )

    def bulk_create(self, objs, **kwargs):
        raise NotImplementedError(
            "Direct .bulk_create() is blocked. Save objects individually."
        )

    def delete(self):
        if settings.DEBUG:
            return super().delete()
        raise NotImplementedError("Bulk delete is blocked.")

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
    def get_queryset(self):
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
        return OperationQuerySet(self.model, using=self._db)
