from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction


class Command(BaseCommand):
    help = (
        "Backfill ProductLedgerEntry rows from existing Operation items. "
        "Safe to re-run — get_or_create skips already-written entries."
    )

    def handle(self, *args, **options):
        from apps.app_inventory.models import ProductLedgerEntry
        from apps.app_operation.models.operation import Operation

        operations = (
            Operation.objects.filter(items__isnull=False)
            .prefetch_related("items__products")
            .distinct()
            .order_by("date", "pk")
        )

        total_created = total_skipped = 0

        for op in operations:
            with db_transaction.atomic():
                created, skipped = ProductLedgerEntry.record(op)
                total_created += created
                total_skipped += skipped

                # If the operation was reversed, also write the negating entries.
                if op.reversed_by_id is not None:
                    created, skipped = ProductLedgerEntry.record(op, negate=True)
                    total_created += created
                    total_skipped += skipped

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created {total_created} entries, skipped {total_skipped} (already existed)."
            )
        )
