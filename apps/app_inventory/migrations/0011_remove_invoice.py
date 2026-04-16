from django.db import migrations, models
import django.db.models.deletion


def migrate_items_to_operation(apps, schema_editor):
    schema_editor.execute(
        """
        UPDATE app_inventory_invoiceitem
        SET operation_id = (
            SELECT operation_id
            FROM app_inventory_invoice
            WHERE app_inventory_invoice.id = app_inventory_invoiceitem.invoice_id
        )
        WHERE invoice_id IS NOT NULL
        """
    )


class Migration(migrations.Migration):

    dependencies = [
        ("app_inventory", "0010_invoiceitemadjustment_invoiceitemadjustmentline"),
        ("app_operation", "0011_invoiceitemadjustment_invoiceitemadjustmentline"),
    ]

    operations = [
        # 1. Add operation FK (nullable) so existing rows are valid during migration
        migrations.AddField(
            model_name="invoiceitem",
            name="operation",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="items",
                to="app_operation.operation",
                verbose_name="operation",
            ),
        ),
        # 2. Back-fill from the Invoice intermediary
        migrations.RunPython(
            migrate_items_to_operation,
            reverse_code=migrations.RunPython.noop,
        ),
        # 3. Make it non-nullable now that every row has a value
        migrations.AlterField(
            model_name="invoiceitem",
            name="operation",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="items",
                to="app_operation.operation",
                verbose_name="operation",
            ),
        ),
        # 4. Drop the old Invoice FK from InvoiceItem
        migrations.RemoveField(
            model_name="invoiceitem",
            name="invoice",
        ),
        # 5. Delete the Invoice table
        migrations.DeleteModel(
            name="Invoice",
        ),
    ]
