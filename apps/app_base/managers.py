"""Custom model managers and querysets used by the farm models.

:class:`SafeQuerySet` blocks bulk ``update`` / ``bulk_create`` /
``bulk_update`` and soft-deletes rows individually (no bulk hard delete) so
rows only change through validated, individual ``save()`` calls.
:class:`ActiveManager` exposes only non-soft-deleted rows (``deleted_at`` null)
and :data:`DefaultManager` is the default manager factory for models.
"""

from django import conf
from django.db import models
from django.utils.translation import gettext_lazy as _

# TODO use database level constrains for dataintegrity.
# TODO add finiancial period closing


# -----------------------------
# Custom Managers
# -----------------------------
class SafeQuerySet(models.QuerySet):
    """QuerySet that blocks bulk writes and only soft-deletes.

    ``update()`` / ``bulk_create()`` / ``bulk_update()`` raise so rows only
    change through validated, individual ``save()`` calls. ``delete()``
    soft-deletes every row one at a time — there is no bulk hard delete.
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

    def bulk_update(self, objs, fields, **kwargs):
        """Block bulk updates outside ``DEBUG``; require validated individual saves."""
        if conf.settings.DEBUG:
            return super().bulk_update(objs, fields, **kwargs)
        raise NotImplementedError(
            _("Direct .bulk_update() is blocked. Save objects individually.")
        )

    def delete(self):
        """Soft-delete every row in the queryset, one validated save at a time.

        No bulk hard delete: each row is individually soft-deleted so the
        model's ``delete()`` hooks, validation and post-save tasks run. Returns
        the Django-style ``(count, {model_label: count})`` tuple.
        """
        count = 0
        for obj in self:
            obj.delete()
            count += 1
        return count, {self.model._meta.label: count}


class ActiveManager(models.Manager):
    """
    A model manager that return active models only (models that has no delete_at field)
    """

    def get_queryset(self):
        """Return non-soft-deleted rows only."""
        # This overrides the "base" query for everything
        return SafeQuerySet(self.model, using=self._db).filter(deleted_at__isnull=True)


DefaultManager = SafeQuerySet.as_manager()
