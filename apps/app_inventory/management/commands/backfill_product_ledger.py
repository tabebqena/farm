from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction


class Command(BaseCommand):
    help = (
        "Backfill ProductLedgerEntry rows from existing Invoice records. "
        "Safe to re-run — get_or_create skips already-written entries."
    )

    def handle(self, *args, **options):
        from apps.app_inventory.models import Invoice, ProductLedgerEntry

        invoices = (
            Invoice.objects.select_related("operation")
            .prefetch_related("items__products")
            .order_by("operation__date", "pk")
        )

        total_created = total_skipped = 0

        for invoice in invoices:
            with db_transaction.atomic():
                created, skipped = ProductLedgerEntry.record(invoice)
                total_created += created
                total_skipped += skipped

                # If the operation was reversed, also write the negating entries.
                if invoice.operation.reversed_by_id is not None:
                    created, skipped = ProductLedgerEntry.record(
                        invoice, negate=True
                    )
                    total_created += created
                    total_skipped += skipped

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created {total_created} entries, skipped {total_skipped} (already existed)."
            )
        )
