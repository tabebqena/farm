from django.db import models


class AdjustmentEffect(models.TextChoices):
    INCREASE = "INCREASE", "Increase Original Amount"
    DECREASE = "DECREASE", "Decrease Original Amount"
