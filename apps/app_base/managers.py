from django import conf
from django.db import models

# TODO use database level constrains for dataintegrity.
# TODO add finiancial period closing


# -----------------------------
# Custom Managers
# -----------------------------
class SafeQuerySet(models.QuerySet):
    # This handles bulk deletion: Product.objects.filter(...).delete()
    # def delete(self):
    #     return self.update(deleted_at=timezone.now())
    def update(self, **kwargs):
        raise NotImplementedError(
            "Direct .update() is blocked. Use individual .save() for validation."
        )

    def bulk_create(self, objs, **kwargs):
        raise NotImplementedError(
            "Direct .bulk_create() is blocked. Save objects individually."
        )

    def bulk_update(self, objs, fields, **kwargs):
        if conf.settings.DEBUG:
            return super().bulk_update(objs, fields, **kwargs)
        raise NotImplementedError(
            "Direct .bulk_update() is blocked.  Save objects individually."
        )

    def delete(self):
        if conf.settings.DEBUG:
            return super().delete()

        raise NotImplementedError(
            f"Bulk delete is blocked for {self.model.__name__}. "
            "If this is intended, set 'deletable = True' in the model Meta or class."
        )


class ActiveManager(models.Manager):
    """
    A model manager that return active models only (models that has no delete_at field)
    """

    def get_queryset(self):
        # This overrides the "base" query for everything
        return SafeQuerySet(self.model, using=self._db).filter(deleted_at__isnull=True)


DefaultManager = SafeQuerySet.as_manager()
