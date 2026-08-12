from django.db import migrations


def copy_medical_records(apps, schema_editor):
    """Move MedicalRecord rows from app_inventory to app_animal.

    Raw SQL preserves every column (including created_at/updated_at/deleted_at
    and soft-deleted rows) exactly. The old table is dropped by DeleteModel
    afterwards.
    """
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO app_animal_medicalrecord
                (id, created_at, updated_at, deleted_at, deletable,
                 product_id, date, record_type, status, next_due_date, notes, officer_id)
            SELECT id, created_at, updated_at, deleted_at, deletable,
                 product_id, date, record_type, status, next_due_date, notes, officer_id
            FROM app_inventory_medicalrecord
            """
        )


class Migration(migrations.Migration):

    dependencies = [
        ("app_inventory", "0012_animal_product_template_fields"),
        ("app_animal", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(copy_medical_records, migrations.RunPython.noop),
        migrations.DeleteModel(name="MedicalRecord"),
    ]
