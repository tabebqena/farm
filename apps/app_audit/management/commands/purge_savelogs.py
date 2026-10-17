"""``manage.py purge_savelogs`` — physically delete accumulated audit rows.

The audit trail is append-only and grows with every model save, so this
maintenance command is the ops counterpart that trims it. Unlike the domain
models, audit rows are never soft-deleted: this performs a real ``DELETE``.

Examples::

    manage.py purge_savelogs --older-than 90
    manage.py purge_savelogs --before 2026-01-01
    manage.py purge_savelogs --level derived-only --older-than 30
    manage.py purge_savelogs --trace 1234
    manage.py purge_savelogs --model app_operation.Operation --dry-run
"""

from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.app_base.logging_utils import audit_logger
from apps.app_audit.models import ActionTrace, SaveLog


class Command(BaseCommand):
    help = (
        "Physically remove SaveLog rows (and, by default, the ActionTrace rows "
        "left with no saves) to trim the append-only audit trail."
    )

    requires_migrations_checks = True

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than",
            type=int,
            default=0,
            metavar="DAYS",
            help="Only purge rows created more than DAYS days ago (default 0 = all).",
        )
        parser.add_argument(
            "--before",
            metavar="YYYY-MM-DD",
            help="Only purge rows created before this date.",
        )
        parser.add_argument(
            "--trace",
            type=int,
            metavar="ID",
            help="Only purge the saves belonging to this ActionTrace id.",
        )
        parser.add_argument(
            "--level",
            choices=("all", "derived-only"),
            default="all",
            help="Purge every save or only auto-created (derived) ones.",
        )
        parser.add_argument(
            "--model",
            metavar="APP.Model",
            help="Only purge saves for this model (e.g. app_operation.Operation).",
        )
        parser.add_argument(
            "--keep-traces",
            action="store_true",
            help="Keep ActionTrace rows instead of deleting the ones left empty.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Delete this many rows per batch (default 1000).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be purged without deleting anything.",
        )

    def handle(self, *args, **options):
        cutoff = self._cutoff(options)
        qs = self._savelog_queryset(options, cutoff)
        total = qs.count()

        if not total:
            self.stdout.write("No save logs matched.")
            return

        if options["dry_run"]:
            self.stdout.write(
                f"  would purge {total} save log row(s)"
                + ("" if options["keep_traces"] else " and any orphaned traces")
            )
            self.stdout.write(self.style.WARNING("Dry run — nothing was deleted."))
            return

        batch_size = max(1, options["batch_size"])
        deleted = 0
        while True:
            pks = list(qs.order_by("pk").values_list("pk", flat=True)[:batch_size])
            if not pks:
                break
            deleted += SaveLog.objects.filter(pk__in=pks).delete()[0]

        self.stdout.write(
            self.style.SUCCESS(f"Purged {deleted} save log row(s).")
        )

        traces_deleted = 0
        if not options["keep_traces"]:
            traces_deleted = self._purge_orphan_traces(cutoff)
            if traces_deleted:
                self.stdout.write(
                    self.style.SUCCESS(f"Purged {traces_deleted} orphaned trace(s).")
                )

        audit_logger.info(
            f"savelogs_purged | save_logs={deleted} | traces={traces_deleted} | "
            f"user=purge_savelogs_command"
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _cutoff(self, options):
        cutoff = None
        if options["older_than"] > 0:
            cutoff = timezone.now() - timedelta(days=options["older_than"])
        if options["before"]:
            try:
                parsed = datetime.strptime(options["before"], "%Y-%m-%d").date()
            except ValueError as exc:
                raise CommandError("--before must be YYYY-MM-DD.") from exc
            before_dt = timezone.make_aware(
                datetime.combine(parsed, time.min),
                timezone.get_current_timezone(),
            )
            if cutoff is None or before_dt < cutoff:
                cutoff = before_dt
        return cutoff

    def _savelog_queryset(self, options, cutoff):
        qs = SaveLog.objects.all()
        if cutoff is not None:
            qs = qs.filter(created_at__lt=cutoff)
        if options["trace"]:
            qs = qs.filter(trace_id=options["trace"])
        if options["level"] == "derived-only":
            qs = qs.filter(is_derived=True)
        if options["model"]:
            try:
                app_label, _, model_name = options["model"].partition(".")
                if not app_label or not model_name:
                    raise ValueError
            except ValueError as exc:
                raise CommandError("--model must be APP.Model.") from exc
            qs = qs.filter(app_label=app_label, model=model_name.lower())
        return qs

    def _purge_orphan_traces(self, cutoff):
        qs = ActionTrace.objects.filter(saves__isnull=True)
        if cutoff is not None:
            qs = qs.filter(created_at__lt=cutoff)
        return qs.delete()[0]
