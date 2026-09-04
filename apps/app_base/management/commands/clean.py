"""``manage.py clean`` — hard-delete accumulated soft-deleted rows.

Soft delete (``deleted_at``) keeps every row forever, so tombstones accumulate
over time. This maintenance command is the admin/ops counterpart that
physically removes those tombstones. It:

- never touches live rows (only rows with ``deleted_at`` set),
- respects the ``PROTECT`` schema: a tombstone that is still referenced by any
  other row (live or soft-deleted) is skipped until its dependents are purged
  first — leaf-up, mirroring the soft-delete deletion order,
- deletes in rounds so a parent tombstone is purged once its tombstone
  children have gone first.

Deletion goes through Django's deletion collector (raw SQL), so the model
soft-delete override is bypassed but FK ``PROTECT`` semantics are enforced.

Examples::

    manage.py clean                          # purge every tombstone possible
    manage.py clean --older-than 90          # only tombstones older than 90 days
    manage.py clean --model app_entity.Entity
    manage.py clean --dry-run                # report only
"""

from datetime import timedelta

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, transaction
from django.db.models.deletion import Collector, ProtectedError
from django.utils import timezone

from apps.app_base.logging_utils import audit_logger, logger


class Command(BaseCommand):
    help = (
        "Physically delete (purge) soft-deleted rows that accumulated over time. "
        "Live rows are never touched; tombstones still referenced by other rows "
        "are skipped until their dependents are purged first."
    )

    requires_migrations_checks = True

    def add_arguments(self, parser):
        parser.add_argument(
            "--model",
            metavar="APP.Model",
            help="Only purge this model (default: every model with a deleted_at field).",
        )
        parser.add_argument(
            "--older-than",
            type=int,
            default=0,
            metavar="DAYS",
            help="Only purge tombstones deleted more than DAYS days ago (default 0 = all).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be purged without deleting anything.",
        )

    # ------------------------------------------------------------------ #
    # Command body
    # ------------------------------------------------------------------ #

    def handle(self, *args, **options):
        models = self._target_models(options["model"])
        cutoff = None
        if options["older_than"] > 0:
            cutoff = timezone.now() - timedelta(days=options["older_than"])

        # model -> list[pk] of tombstones still present and candidates to purge
        pending = {}
        for model in models:
            qs = self._tombstone_qs(model, cutoff)
            pks = list(qs.order_by("pk").values_list("pk", flat=True))
            if pks:
                pending[model] = pks

        if not pending:
            self.stdout.write("No soft-deleted rows to purge.")
            return

        if options["dry_run"]:
            for model, pks in pending.items():
                self.stdout.write(
                    f"  would purge {len(pks)} {model._meta.label_lower} row(s)"
                )
            self.stdout.write(self.style.WARNING("Dry run — nothing was deleted."))
            return

        purged = {model: 0 for model in models}
        self.stdout.write("Purging soft-deleted rows (leaf-up)…")

        # Rounds: a tombstone that is blocked only by other tombstones becomes
        # purged as soon as its dependents have been removed in an earlier pass.
        while pending:
            progress = False
            for model in list(pending):
                pks = pending[model]
                remaining = []
                rows = list(
                    self._tombstone_qs(model, None)
                    .filter(pk__in=pks)
                    .order_by("pk")
                )
                for obj in rows:
                    if self._purge_one(model, obj):
                        purged[model] += 1
                        progress = True
                    else:
                        remaining.append(obj.pk)
                if remaining:
                    pending[model] = remaining
                else:
                    del pending[model]
            if not progress:
                break

        self.stdout.write("Purge summary:")
        total_purged = 0
        total_skipped = 0
        for model in sorted(models, key=lambda m: m._meta.label_lower):
            count_purged = purged[model]
            count_skipped = len(pending.get(model, ()))
            if count_purged or count_skipped:
                total_purged += count_purged
                total_skipped += count_skipped
                self.stdout.write(
                    f"  {model._meta.label_lower}: purged {count_purged}, "
                    f"still referenced {count_skipped}"
                )
        self.stdout.write(
            self.style.SUCCESS(
                f"Total purged: {total_purged}; "
                f"skipped (still referenced): {total_skipped}"
            )
        )
        if total_skipped:
            self.stdout.write(
                self.style.WARNING(
                    "Skipped tombstones are still referenced by other rows. "
                    "Purge their dependents (or run the command again later) "
                    "to remove them."
                )
            )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _target_models(self, model_spec):
        """Resolve the models to scan (option-filtered or every soft-delete model)."""
        if model_spec:
            try:
                app_label, _, model_name = model_spec.partition(".")
                model = django_apps.get_model(app_label, model_name)
            except LookupError as exc:
                raise CommandError(f"Unknown model '{model_spec}'.") from exc
            if not self._has_soft_delete(model):
                raise CommandError(
                    f"Model '{model_spec}' has no deleted_at field — nothing to purge."
                )
            return [model]

        models = [
            model
            for model in django_apps.get_models()
            if not model._meta.proxy
            and not model._meta.auto_created
            and self._has_soft_delete(model)
        ]
        return sorted(models, key=lambda m: m._meta.label_lower)

    @staticmethod
    def _has_soft_delete(model):
        return any(f.name == "deleted_at" for f in model._meta.fields)

    @staticmethod
    def _tombstone_qs(model, cutoff):
        """QuerySet of the model's soft-deleted rows (optionally older than *cutoff*)."""
        manager = getattr(model, "all_objects", model._default_manager)
        qs = manager.filter(deleted_at__isnull=False)
        if cutoff is not None:
            qs = qs.filter(deleted_at__lt=cutoff)
        return qs

    def _purge_one(self, model, obj) -> bool:
        """Hard-delete *obj* via Django's deletion collector.

        Returns True when the row was physically removed. Returns False when the
        row is still referenced (``PROTECT``) or could not be deleted, leaving it
        for a later round / report.
        """
        try:
            with transaction.atomic(using=DEFAULT_DB_ALIAS):
                collector = Collector(using=DEFAULT_DB_ALIAS)
                collector.collect([obj])
                collector.delete()
        except ProtectedError:
            return False
        except Exception:
            logger.exception(
                "clean: failed to purge %s pk=%s", model._meta.label_lower, obj.pk
            )
            return False

        deleted_at = obj.deleted_at.isoformat() if obj.deleted_at else ""
        audit_logger.info(
            f"{model._meta.model_name}_purged | {model.__name__}:{obj.pk} | "
            f"user=clean_command | deleted_at={deleted_at}"
        )
        return True
