"""Admin mixin that makes the soft-delete guard authoritative for deletes.

Django admin decides whether a delete is allowed from
:meth:`ModelAdmin.get_deleted_objects`, which runs Django's database deletion
collector. That collector sees **every** row — soft-deleted tombstones included
— and every ``on_delete=PROTECT`` relation, so it refuses deletes our
:meth:`~apps.app_base.models.BaseModel.delete` guard would allow (and that the
guard would auto soft-delete). It also lists tombstones and owned
``_delete_auto_relations`` rows as blocking "protected" objects.

:class:`SoftDeleteAdminGuardMixin` re-points the admin decision at the same
live-only, auto-relation-aware guard the model uses
(``get_delete_blockers()``): tombstones and owned rows stop blocking, live
financial dependents are still refused, and the guard's own message is shown.
A ``ValidationError`` raised on the confirming request is surfaced as an admin
error message instead of a 500.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect


class SoftDeleteAdminGuardMixin:
    """Make Django-admin deletes honour ``BaseModel``'s soft-delete guard.

    Mix in before :class:`django.contrib.admin.ModelAdmin` on any admin class
    whose model uses the project's soft delete / ``PROTECT`` conventions.
    """

    def get_deleted_objects(self, objs, request):
        """Replace the collector's ``protected`` list with the model guard's.

        The collector's "what else would be deleted" list is kept, but its
        ``protected`` set is discarded: under soft delete it wrongly counts
        tombstones and owned auto-relation rows. The guard's
        ``get_delete_blockers()`` is live-only and excludes
        ``_delete_auto_relations``, so it names exactly what must be removed
        first.
        """
        deleted_objects, model_count, perms_needed, _ = super().get_deleted_objects(
            objs, request
        )
        protected = []
        for obj in objs:
            get_blockers = getattr(obj, "get_delete_blockers", None)
            if callable(get_blockers):
                protected.extend(get_blockers())
        return deleted_objects, model_count, perms_needed, protected

    def delete_view(self, request, object_id, extra_context=None):
        """Surface a guard refusal as an admin message instead of a 500."""
        try:
            return super().delete_view(request, object_id, extra_context)
        except ValidationError as exc:
            self.message_user(request, " ".join(exc.messages), level=messages.ERROR)
            return HttpResponseRedirect(request.get_full_path())
