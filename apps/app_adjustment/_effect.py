from django.db import models
from django.utils.translation import gettext_lazy as _


class AdjustmentEffect(models.TextChoices):
    INCREASE = "INCREASE", _("Increase Original Amount")
    DECREASE = "DECREASE", _("Decrease Original Amount")
