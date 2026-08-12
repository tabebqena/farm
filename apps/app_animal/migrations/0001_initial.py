import datetime

import django.db.models.deletion
import django.db.models.manager
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="MedicalRecord",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="created at"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="updated at"),
                ),
                (
                    "deleted_at",
                    models.DateTimeField(
                        blank=True, default=None, null=True, verbose_name="deleted at"
                    ),
                ),
                ("deletable", models.BooleanField(default=False, verbose_name="deletable")),
                (
                    "date",
                    models.DateField(default=datetime.date.today, verbose_name="date"),
                ),
                (
                    "record_type",
                    models.CharField(
                        choices=[
                            ("CHECKUP", "Check-up"),
                            ("VACCINATION", "Vaccination"),
                            ("TREATMENT", "Treatment"),
                            ("DIAGNOSIS", "Diagnosis"),
                            ("OTHER", "Other"),
                        ],
                        max_length=20,
                        verbose_name="record type",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("HEALTHY", "Healthy"),
                            ("SICK", "Sick"),
                            ("UNDER_TREATMENT", "Under treatment"),
                            ("RECOVERED", "Recovered"),
                            ("UNKNOWN", "Unknown"),
                        ],
                        default="UNKNOWN",
                        help_text="Health status at the time this record was made.",
                        max_length=20,
                        verbose_name="status",
                    ),
                ),
                (
                    "next_due_date",
                    models.DateField(
                        blank=True,
                        help_text="e.g. next vaccination.",
                        null=True,
                        verbose_name="next due date",
                    ),
                ),
                ("notes", models.TextField(blank=True, verbose_name="notes")),
                (
                    "officer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="officer",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        help_text="The animal this medical record belongs to.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="medical_records",
                        to="app_inventory.product",
                        verbose_name="product",
                    ),
                ),
            ],
            options={
                "verbose_name": "medical record",
                "verbose_name_plural": "medical records",
                "ordering": ["-date", "-created_at"],
            },
            managers=[
                ("all_objects", django.db.models.manager.Manager()),
            ],
        ),
    ]
