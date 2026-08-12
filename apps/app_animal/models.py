from datetime import date as today_date

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.app_base.models import BaseModel


class MedicalRecord(BaseModel):
    """
    A health/veterinary record linked to an individual animal (a Product with an
    ANIMAL product template).

    Health state is captured per record via ``status`` (there is no single
    ``health_status`` field on Product).
    """

    class RecordType(models.TextChoices):
        CHECKUP = "CHECKUP", _("Check-up")
        VACCINATION = "VACCINATION", _("Vaccination")
        TREATMENT = "TREATMENT", _("Treatment")
        DIAGNOSIS = "DIAGNOSIS", _("Diagnosis")
        OTHER = "OTHER", _("Other")

    class HealthStatus(models.TextChoices):
        HEALTHY = "HEALTHY", _("Healthy")
        SICK = "SICK", _("Sick")
        UNDER_TREATMENT = "UNDER_TREATMENT", _("Under treatment")
        RECOVERED = "RECOVERED", _("Recovered")
        UNKNOWN = "UNKNOWN", _("Unknown")

    product = models.ForeignKey(
        "app_inventory.Product",
        on_delete=models.PROTECT,
        related_name="medical_records",
        verbose_name=_("product"),
        help_text=_("The animal this medical record belongs to."),
    )
    date = models.DateField(_("date"), default=today_date.today)
    record_type = models.CharField(
        _("record type"), choices=RecordType.choices, max_length=20
    )
    status = models.CharField(
        _("status"),
        choices=HealthStatus.choices,
        max_length=20,
        default=HealthStatus.UNKNOWN,
        help_text=_("Health status at the time this record was made."),
    )
    next_due_date = models.DateField(
        _("next due date"), null=True, blank=True, help_text=_("e.g. next vaccination.")
    )
    notes = models.TextField(_("notes"), blank=True)
    officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("officer"),
    )

    class Meta:
        verbose_name = _("medical record")
        verbose_name_plural = _("medical records")
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.product} – {self.get_record_type_display()} ({self.date})"
