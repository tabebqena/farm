# Generated manually to bridge model changes after git checkout restored old state

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_inventory", "0006_alter_producttemplate_unique_together_and_more"),
        ("app_operation", "0007_remove_financialperiod_amount"),
    ]

    operations = [
        # Rename InvoiceItem.product → product_template (db_column="product_id"
        # preserves the existing database column name).
        migrations.RenameField(
            model_name="invoiceitem",
            old_name="product",
            new_name="product_template",
        ),
        migrations.AlterField(
            model_name="invoiceitem",
            name="product_template",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="invoice_items",
                to="app_inventory.producttemplate",
                verbose_name="product template",
                db_column="product_id",
            ),
        ),
        # Add direct product FK to InventoryMovementLine (nullable for migration
        # safety; Python code always sets it before saving).
        migrations.AddField(
            model_name="inventorymovementline",
            name="product",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="movement_lines",
                to="app_inventory.product",
                verbose_name="product",
            ),
        ),
        # Add officer FK to InventoryMovementLine (nullable for migration safety;
        # Python code always sets it before saving).
        migrations.AddField(
            model_name="inventorymovementline",
            name="officer",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="movement_lines_supervised",
                to=settings.AUTH_USER_MODEL,
                verbose_name="officer",
            ),
        ),
    ]
